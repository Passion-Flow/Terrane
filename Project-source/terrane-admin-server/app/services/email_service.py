"""Email service (generic SMTP) — covers any SMTP-capable mailbox/ESP.

A single robust SMTP sending implementation covers: raw SMTP + 163/126/QQ/Tencent Enterprise/Aliyun/Gmail/Outlook...
plus the SMTP relays of ESPs such as SES/SendGrid/Aliyun DM/Tencent SES/Mailgun/Postmark/Resend/Brevo/Mailjet
(9 out of 10 ESPs offer an SMTP relay, so per-provider API adapters are unnecessary; APIs are only
brought in when templates/events/batching are needed).

Connection modes (encryption):
  ssl       Implicit TLS (encrypted on connect; 465/994, the default for domestic mailboxes) -> SMTP_SSL
  starttls  Plaintext connect then STARTTLS upgrade (587) -> SMTP + starttls + a second EHLO (mandated by RFC 3207)
  none      Plaintext (25); opportunistic upgrade if the server advertises STARTTLS
  auto      Inferred from the port: 465/994 -> ssl, 587 -> starttls, otherwise -> none

Sender: the From header supports a display name ("Terrane <addr>"); the envelope MAIL FROM is forced
to the sender address (163/QQ and others require From = the authenticated account, otherwise they
reject with 553/554 DT:SUM).

Error normalization: maps SMTP 535/553/554/530/421/450 and so on into actionable hints (the frontend
uses them to give precise guidance).
Runs in a thread pool (asyncio.to_thread) to avoid blocking the event loop; stdlib smtplib, zero third-party dependencies.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

from app.core.errors import BizError

_IMPLICIT_SSL_PORTS = frozenset({465, 994, 2465})


def resolve_encryption(encryption: str | None, port: int) -> str:
    """Normalize the connection mode; auto is inferred from the port."""
    enc = (encryption or "auto").strip().lower()
    if enc in ("ssl", "starttls", "none"):
        return enc
    # auto / unknown -> by port
    if port in _IMPLICIT_SSL_PORTS:
        return "ssl"
    if port == 587:
        return "starttls"
    return "none"


def _context(allow_insecure: bool) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if allow_insecure:
        # Self-signed certificate on an internal network: disable hostname checking first, then downgrade verify (verify cannot be downgraded while hostname checking is enabled).
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _build_message(cfg: dict[str, Any], to: str, subject: str, body: str) -> tuple[EmailMessage, str]:
    from_addr = (cfg.get("from_address") or cfg.get("username") or "no-reply@terrane.local").strip()
    from_name = (cfg.get("from_name") or "Terrane").strip()
    msg = EmailMessage()
    msg["From"] = formataddr((from_name, from_addr))  # Non-ASCII display names are automatically RFC2047-encoded
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return msg, from_addr


def _send_sync(cfg: dict[str, Any], to: str, subject: str, body: str) -> None:
    host = (cfg.get("host") or "localhost").strip()
    port = int(cfg.get("port") or 25)
    enc = resolve_encryption(cfg.get("encryption"), port)
    username = cfg.get("username") or ""
    from app.services import crypto
    password = crypto.decrypt(cfg.get("password"))   # KEK decryption (compatible with legacy plaintext)
    allow_insecure = bool(cfg.get("allow_insecure"))
    timeout = float(cfg.get("timeout") or 20)
    ctx = _context(allow_insecure)
    msg, from_addr = _build_message(cfg, to, subject, body)

    if enc == "ssl":
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(host, port, context=ctx, timeout=timeout)
    else:
        smtp = smtplib.SMTP(host, port, timeout=timeout)
    try:
        smtp.ehlo()
        # starttls: explicitly requested -> upgrade; none and the server advertises STARTTLS -> opportunistic upgrade.
        if enc == "starttls" or (enc == "none" and smtp.has_extn("STARTTLS")):
            smtp.starttls(context=ctx)
            smtp.ehlo()  # RFC 3207: EHLO must be re-sent after TLS to re-read capabilities such as AUTH
        if username:
            smtp.login(username, password)
        # Envelope MAIL FROM = sender address (aligned with the From header to satisfy the same-origin check of 163/QQ).
        smtp.send_message(msg, from_addr=from_addr, to_addrs=[to])
    finally:
        try:
            smtp.quit()
        except Exception:  # noqa: BLE001 — ignore errors on close
            pass


def _classify(code: int | None, text: Any) -> str:
    """SMTP failure -> actionable hint (the frontend uses it to give precise guidance)."""
    t = (text.decode(errors="ignore") if isinstance(text, bytes) else str(text or "")).upper()
    if code == 535 or "AUTH" in t and code in (530, 535):
        return "auth_failed"            # Wrong credentials / should use an authorization code / app-specific password
    if code == 530:
        return "auth_or_tls_required"   # Must authenticate first, or run STARTTLS first
    if code == 553 or "DT:SUM" in t or "MUST EQUAL" in t or "AUTHORIZED USER" in t:
        return "from_not_allowed"       # Sender must = the authenticated account (163/QQ)
    if code in (421, 450) or "DT:STC" in t or "MI:STC" in t:
        return "temporary"              # Rate-limited / temporarily unavailable, retry later
    if code in (550, 554) or "DT:SPM" in t or "SPAM" in t:
        return "rejected"               # Rejected by content / policy / anti-spam
    return "smtp_error"


async def send(cfg: dict[str, Any], *, to: str, subject: str, body: str) -> None:
    """Send one email; on failure raise SYSTEM_UNAVAILABLE (details carry a hint + a redacted reason)."""
    try:
        await asyncio.to_thread(_send_sync, cfg, to, subject, body)
    except smtplib.SMTPResponseException as exc:
        raise BizError("SYSTEM_UNAVAILABLE", {
            "service": "email", "hint": _classify(exc.smtp_code, exc.smtp_error),
            "smtp_code": exc.smtp_code,
            "reason": (exc.smtp_error.decode(errors="ignore")
                       if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error))[:200]})
    except smtplib.SMTPAuthenticationError as exc:  # Usually already caught above; this is a fallback
        raise BizError("SYSTEM_UNAVAILABLE", {"service": "email", "hint": "auth_failed",
                                              "reason": str(exc)[:200]})
    except (smtplib.SMTPException, ssl.SSLError, OSError) as exc:
        # Connection/TLS/handshake failures (wrong host or port, unreachable network, mismatched certificate).
        hint = "tls_failed" if isinstance(exc, ssl.SSLError) else "connect_failed"
        raise BizError("SYSTEM_UNAVAILABLE", {"service": "email", "hint": hint,
                                              "reason": str(exc)[:200]})


async def test_smtp(cfg: dict[str, Any], *, to: str) -> None:
    """Connectivity test: send one test email to verify the configuration is reachable. On failure raise SYSTEM_UNAVAILABLE (with a hint)."""
    await send(cfg, to=to, subject="Terrane SMTP Test",
               body="This is an SMTP test email from the Terrane setup wizard. Receiving it means your email configuration is working.")

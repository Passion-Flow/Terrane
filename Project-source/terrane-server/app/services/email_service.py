"""Email service (generic SMTP) — covers any SMTP-capable mailbox/ESP.

One robust SMTP sending implementation covers it all: raw SMTP + 163/126/QQ/Tencent Enterprise/Aliyun/Gmail/Outlook…
plus the SMTP relays of ESPs like SES/SendGrid/Aliyun DM/Tencent SES/Mailgun/Postmark/Resend/Brevo/Mailjet
(9 out of 10 ESPs offer an SMTP relay, so per-ESP API adapters are unnecessary; an API is only added when templates/events/batching are needed).

Connection modes (encryption):
  ssl       Implicit TLS (encrypted on connect; 465/994, the default for Chinese mailboxes) -> SMTP_SSL
  starttls  Plaintext connection then STARTTLS upgrade (587) -> SMTP + starttls + a second EHLO (mandated by RFC 3207)
  none      Plaintext (25); opportunistically upgraded if the server advertises STARTTLS
  auto      Inferred from the port: 465/994 -> ssl, 587 -> starttls, otherwise -> none

Sender: the From header supports a display name ("Terrane <addr>"); the envelope MAIL FROM is forced to equal the sender address
(163/QQ and others require From = the authenticated account, otherwise they reject with 553/554 DT:SUM).

Error normalization: maps SMTP 535/553/554/530/421/450 etc. into actionable hints (the front end gives precise guidance based on these).
Runs in a thread pool (asyncio.to_thread) to avoid blocking the event loop; uses stdlib smtplib with zero third-party dependencies.
"""

from __future__ import annotations

import asyncio
import html as _html
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

from app.core.errors import BizError

_IMPLICIT_SSL_PORTS = frozenset({465, 994, 2465})

# Brand color (petrol-teal, matching the front-end --color-accent). Emails require inline styles + table layout to render reliably in Gmail/Outlook.
_ACCENT = "#0d7d86"


def render_action_email(*, brand: str, title: str, intro: str, button_text: str,
                        link: str, note: str) -> str:
    """A SaaS-style "call to action" email (shared by email verification / password reset). Inline styles, table layout, responsive, clear in both light and dark."""
    b = _html.escape(brand or "Terrane")
    initial = b[0].upper() if b else "T"
    t, i, btn, n = (_html.escape(x) for x in (title, intro, button_text, note))
    safe_link = _html.escape(link, quote=True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"></head>
<body style="margin:0;padding:0;background:#f4f5f7;-webkit-font-smoothing:antialiased;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;padding:40px 16px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#ffffff;border:1px solid #ececf0;border-radius:16px;overflow:hidden;">
        <tr><td style="padding:30px 40px 0;">
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>
            <td style="vertical-align:middle;"><div style="width:36px;height:36px;border-radius:10px;background:{_ACCENT};color:#ffffff;font:700 19px/36px -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;text-align:center;">{initial}</div></td>
            <td style="vertical-align:middle;padding-left:11px;font:600 17px/1 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#18181b;">{b}</td>
          </tr></table>
        </td></tr>
        <tr><td style="padding:26px 40px 0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
          <h1 style="margin:0 0 12px;font-size:21px;font-weight:600;color:#18181b;letter-spacing:-.01em;">{t}</h1>
          <p style="margin:0 0 26px;font-size:14px;line-height:1.65;color:#52525b;">{i}</p>
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>
            <td style="border-radius:11px;background:{_ACCENT};">
              <a href="{safe_link}" target="_blank" style="display:inline-block;padding:13px 32px;font:600 14px/1 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#ffffff;text-decoration:none;border-radius:11px;">{btn}</a>
            </td>
          </tr></table>
          <p style="margin:26px 0 0;font-size:12px;line-height:1.6;color:#a1a1aa;">{n}</p>
          <p style="margin:14px 0 0;font-size:12px;line-height:1.6;color:#a1a1aa;">If the button does not work, copy and paste the link below into your browser:</p>
          <p style="margin:6px 0 0;font-size:12px;line-height:1.5;word-break:break-all;"><a href="{safe_link}" target="_blank" style="color:{_ACCENT};text-decoration:none;">{safe_link}</a></p>
        </td></tr>
        <tr><td style="padding:28px 40px 30px;">
          <div style="border-top:1px solid #f0f0f3;padding-top:18px;font:400 11px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#c0c0c8;">
            This email was sent automatically by {b}; please do not reply directly. If you did not request this, simply ignore this email and nothing will change for your account.
          </div>
        </td></tr>
      </table>
      <div style="max-width:480px;margin:16px auto 0;font:400 11px/1 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#c8c8d0;text-align:center;">© {b}</div>
    </td></tr>
  </table>
</body></html>"""


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
        # Self-signed certificate on an internal network: disable hostname checking before downgrading verify (verify cannot be downgraded while hostname checking is on).
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _build_message(cfg: dict[str, Any], to: str, subject: str, body: str,
                   html: str | None = None) -> tuple[EmailMessage, str]:
    from_addr = (cfg.get("from_address") or cfg.get("username") or "no-reply@terrane.local").strip()
    from_name = (cfg.get("from_name") or "Terrane").strip()
    msg = EmailMessage()
    msg["From"] = formataddr((from_name, from_addr))  # Non-ASCII display names are RFC2047-encoded automatically
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)                         # Plain-text fallback (for clients without HTML rendering + spam-filter friendly)
    if html:
        msg.add_alternative(html, subtype="html")  # multipart/alternative: prefer showing HTML
    return msg, from_addr


def _send_sync(cfg: dict[str, Any], to: str, subject: str, body: str,
               html: str | None = None) -> None:
    host = (cfg.get("host") or "localhost").strip()
    port = int(cfg.get("port") or 25)
    enc = resolve_encryption(cfg.get("encryption"), port)
    username = cfg.get("username") or ""
    from app.services import crypto
    password = crypto.decrypt(cfg.get("password"))   # KEK decryption (compatible with legacy plaintext)
    allow_insecure = bool(cfg.get("allow_insecure"))
    timeout = float(cfg.get("timeout") or 20)
    ctx = _context(allow_insecure)
    msg, from_addr = _build_message(cfg, to, subject, body, html)

    if enc == "ssl":
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(host, port, context=ctx, timeout=timeout)
    else:
        smtp = smtplib.SMTP(host, port, timeout=timeout)
    try:
        smtp.ehlo()
        # starttls: explicitly requested -> upgrade; none and the server advertises STARTTLS -> opportunistic upgrade.
        if enc == "starttls" or (enc == "none" and smtp.has_extn("STARTTLS")):
            smtp.starttls(context=ctx)
            smtp.ehlo()  # RFC 3207: after TLS, EHLO must be resent to re-read AUTH and other capabilities
        if username:
            smtp.login(username, password)
        # Envelope MAIL FROM = the sender address (aligned with the From header to satisfy 163/QQ's same-origin check).
        smtp.send_message(msg, from_addr=from_addr, to_addrs=[to])
    finally:
        try:
            smtp.quit()
        except Exception:  # noqa: BLE001 — ignore errors on close
            pass


def _classify(code: int | None, text: Any) -> str:
    """SMTP failure -> actionable hint (the front end gives precise guidance based on it)."""
    t = (text.decode(errors="ignore") if isinstance(text, bytes) else str(text or "")).upper()
    if code == 535 or "AUTH" in t and code in (530, 535):
        return "auth_failed"            # Wrong credentials / should use an authorization code or app-specific password
    if code == 530:
        return "auth_or_tls_required"   # Must authenticate first, or run STARTTLS first
    if code == 553 or "DT:SUM" in t or "MUST EQUAL" in t or "AUTHORIZED USER" in t:
        return "from_not_allowed"       # Sender must = the authenticated account (163/QQ)
    if code in (421, 450) or "DT:STC" in t or "MI:STC" in t:
        return "temporary"              # Rate-limited / temporarily unavailable, retry later
    if code in (550, 554) or "DT:SPM" in t or "SPAM" in t:
        return "rejected"               # Rejected by content/policy/spam filtering
    return "smtp_error"


async def send(cfg: dict[str, Any], *, to: str, subject: str, body: str,
               html: str | None = None) -> None:
    """Send one email; on failure raise SYSTEM_UNAVAILABLE (details carry a hint + a redacted reason)."""
    try:
        await asyncio.to_thread(_send_sync, cfg, to, subject, body, html)
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
        # Connection/TLS/handshake failures (wrong host or port, network unreachable, certificate mismatch).
        hint = "tls_failed" if isinstance(exc, ssl.SSLError) else "connect_failed"
        raise BizError("SYSTEM_UNAVAILABLE", {"service": "email", "hint": hint,
                                              "reason": str(exc)[:200]})


async def test_smtp(cfg: dict[str, Any], *, to: str) -> None:
    """Connection test: send a test email to verify the configuration is reachable. On failure raise SYSTEM_UNAVAILABLE (with a hint)."""
    await send(cfg, to=to, subject="Terrane SMTP test",
               body="This is an SMTP test email from the Terrane setup wizard. Receiving it means your email configuration is working.")

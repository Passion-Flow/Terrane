"""邮件服务（通用 SMTP）— 覆盖一切支持 SMTP 的邮箱/ESP。

一份健壮的 SMTP 发信实现即可覆盖：raw SMTP + 163/126/QQ/腾讯企业/阿里/Gmail/Outlook…
+ SES/SendGrid/Aliyun DM/Tencent SES/Mailgun/Postmark/Resend/Brevo/Mailjet 等 ESP 的 SMTP 中继
（9/10 ESP 都提供 SMTP relay，故无需逐个 API 适配器；API 仅在需要模板/事件/批量时才上）。

连接模式（encryption）：
  ssl       隐式 TLS（连上即加密；465/994，国内邮箱默认）→ SMTP_SSL
  starttls  明文连接后 STARTTLS 升级（587）→ SMTP + starttls + 二次 EHLO（RFC 3207 强制）
  none      明文（25）；若服务端通告 STARTTLS 则机会性升级
  auto      按端口推断：465/994→ssl，587→starttls，其它→none

发件人：From 头支持显示名（"Terrane <addr>"），信封 MAIL FROM 强制=发件地址
（163/QQ 等要求 From=认证账号，否则 553/554 DT:SUM 拒发）。

错误归一：把 SMTP 535/553/554/530/421/450 等映射成可操作的 hint（前端据此给精准提示）。
跑线程池（asyncio.to_thread）避免阻塞事件循环；stdlib smtplib，零三方依赖。
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
    """归一连接模式；auto 按端口推断。"""
    enc = (encryption or "auto").strip().lower()
    if enc in ("ssl", "starttls", "none"):
        return enc
    # auto / 未知 → 按端口
    if port in _IMPLICIT_SSL_PORTS:
        return "ssl"
    if port == 587:
        return "starttls"
    return "none"


def _context(allow_insecure: bool) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if allow_insecure:
        # 内网自签证书场景：顺序要先关 hostname 再降级 verify（启用 hostname 校验时不可降级）。
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _build_message(cfg: dict[str, Any], to: str, subject: str, body: str) -> tuple[EmailMessage, str]:
    from_addr = (cfg.get("from_address") or cfg.get("username") or "no-reply@terrane.local").strip()
    from_name = (cfg.get("from_name") or "Terrane").strip()
    msg = EmailMessage()
    msg["From"] = formataddr((from_name, from_addr))  # 非 ASCII 显示名自动 RFC2047 编码
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
    password = crypto.decrypt(cfg.get("password"))   # KEK 解密(兼容历史明文)
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
        # starttls：显式要求 → 升级；none 且服务端通告 STARTTLS → 机会性升级。
        if enc == "starttls" or (enc == "none" and smtp.has_extn("STARTTLS")):
            smtp.starttls(context=ctx)
            smtp.ehlo()  # RFC 3207：TLS 后必须重发 EHLO 以重读 AUTH 等能力
        if username:
            smtp.login(username, password)
        # 信封 MAIL FROM = 发件地址（与 From 头对齐，满足 163/QQ 的同源校验）。
        smtp.send_message(msg, from_addr=from_addr, to_addrs=[to])
    finally:
        try:
            smtp.quit()
        except Exception:  # noqa: BLE001 — 关闭异常忽略
            pass


def _classify(code: int | None, text: Any) -> str:
    """SMTP 失败 → 可操作 hint（前端据此给精准提示）。"""
    t = (text.decode(errors="ignore") if isinstance(text, bytes) else str(text or "")).upper()
    if code == 535 or "AUTH" in t and code in (530, 535):
        return "auth_failed"            # 凭据错/该用授权码/应用专用密码
    if code == 530:
        return "auth_or_tls_required"   # 需先认证或先 STARTTLS
    if code == 553 or "DT:SUM" in t or "MUST EQUAL" in t or "AUTHORIZED USER" in t:
        return "from_not_allowed"       # 发件人须=认证账号（163/QQ）
    if code in (421, 450) or "DT:STC" in t or "MI:STC" in t:
        return "temporary"              # 限速/暂时不可用，稍后重试
    if code in (550, 554) or "DT:SPM" in t or "SPAM" in t:
        return "rejected"               # 内容/策略/反垃圾拒收
    return "smtp_error"


async def send(cfg: dict[str, Any], *, to: str, subject: str, body: str) -> None:
    """发送一封邮件；失败抛 SYSTEM_UNAVAILABLE（details 带 hint + 脱敏原因）。"""
    try:
        await asyncio.to_thread(_send_sync, cfg, to, subject, body)
    except smtplib.SMTPResponseException as exc:
        raise BizError("SYSTEM_UNAVAILABLE", {
            "service": "email", "hint": _classify(exc.smtp_code, exc.smtp_error),
            "smtp_code": exc.smtp_code,
            "reason": (exc.smtp_error.decode(errors="ignore")
                       if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error))[:200]})
    except smtplib.SMTPAuthenticationError as exc:  # 一般已被上面捕获，兜底
        raise BizError("SYSTEM_UNAVAILABLE", {"service": "email", "hint": "auth_failed",
                                              "reason": str(exc)[:200]})
    except (smtplib.SMTPException, ssl.SSLError, OSError) as exc:
        # 连接/TLS/握手类失败（主机端口错、网络不通、证书不符）。
        hint = "tls_failed" if isinstance(exc, ssl.SSLError) else "connect_failed"
        raise BizError("SYSTEM_UNAVAILABLE", {"service": "email", "hint": hint,
                                              "reason": str(exc)[:200]})


async def test_smtp(cfg: dict[str, Any], *, to: str) -> None:
    """测连：发送一封测试邮件，验证配置可达。失败抛 SYSTEM_UNAVAILABLE（含 hint）。"""
    await send(cfg, to=to, subject="Terrane SMTP 测试",
               body="这是一封来自 Terrane 初始化向导的 SMTP 测试邮件。收到即代表邮件配置可用。")

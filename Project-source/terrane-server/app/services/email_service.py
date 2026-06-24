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
import html as _html
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

from app.core.errors import BizError

_IMPLICIT_SSL_PORTS = frozenset({465, 994, 2465})

# 品牌色（petrol-teal，与前端 --color-accent 一致）。邮件必须内联样式 + 表格布局才能在 Gmail/Outlook 稳定渲染。
_ACCENT = "#0d7d86"


def render_action_email(*, brand: str, title: str, intro: str, button_text: str,
                        link: str, note: str) -> str:
    """SaaS 风格的「行动邀请」邮件（验证邮箱 / 重置密码通用）。内联样式、表格布局、响应式、深浅皆清晰。"""
    b = _html.escape(brand or "Terrane")
    initial = b[0].upper() if b else "T"
    t, i, btn, n = (_html.escape(x) for x in (title, intro, button_text, note))
    safe_link = _html.escape(link, quote=True)
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
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
          <p style="margin:14px 0 0;font-size:12px;line-height:1.6;color:#a1a1aa;">若按钮无法点击，请复制下方链接到浏览器打开：</p>
          <p style="margin:6px 0 0;font-size:12px;line-height:1.5;word-break:break-all;"><a href="{safe_link}" target="_blank" style="color:{_ACCENT};text-decoration:none;">{safe_link}</a></p>
        </td></tr>
        <tr><td style="padding:28px 40px 30px;">
          <div style="border-top:1px solid #f0f0f3;padding-top:18px;font:400 11px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#c0c0c8;">
            此邮件由 {b} 自动发送，请勿直接回复。如果这不是你本人的操作，忽略本邮件即可，你的账户不会有任何变化。
          </div>
        </td></tr>
      </table>
      <div style="max-width:480px;margin:16px auto 0;font:400 11px/1 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#c8c8d0;text-align:center;">© {b}</div>
    </td></tr>
  </table>
</body></html>"""


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


def _build_message(cfg: dict[str, Any], to: str, subject: str, body: str,
                   html: str | None = None) -> tuple[EmailMessage, str]:
    from_addr = (cfg.get("from_address") or cfg.get("username") or "no-reply@terrane.local").strip()
    from_name = (cfg.get("from_name") or "Terrane").strip()
    msg = EmailMessage()
    msg["From"] = formataddr((from_name, from_addr))  # 非 ASCII 显示名自动 RFC2047 编码
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)                         # 纯文本兜底（无 HTML 渲染的客户端 + 反垃圾友好）
    if html:
        msg.add_alternative(html, subtype="html")  # multipart/alternative：优先展示 HTML
    return msg, from_addr


def _send_sync(cfg: dict[str, Any], to: str, subject: str, body: str,
               html: str | None = None) -> None:
    host = (cfg.get("host") or "localhost").strip()
    port = int(cfg.get("port") or 25)
    enc = resolve_encryption(cfg.get("encryption"), port)
    username = cfg.get("username") or ""
    from app.services import crypto
    password = crypto.decrypt(cfg.get("password"))   # KEK 解密(兼容历史明文)
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


async def send(cfg: dict[str, Any], *, to: str, subject: str, body: str,
               html: str | None = None) -> None:
    """发送一封邮件；失败抛 SYSTEM_UNAVAILABLE（details 带 hint + 脱敏原因）。"""
    try:
        await asyncio.to_thread(_send_sync, cfg, to, subject, body, html)
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

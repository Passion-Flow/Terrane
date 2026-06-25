"""SMTP presets for email providers (one-click fill of host/port/encryption + credential hints).

Based on 2026-06 research: nearly all China-based mailboxes use implicit SSL on port 465
(port 25 is widely blocked by cloud vendors/ISPs), and the password is usually an
"authorization code / client-specific password" rather than the login password; From must
equal the authenticated account (163/QQ). A single generic SMTP implementation plus these
presets covers consumer mailboxes, business email, and the SMTP relays of the major ESPs.
`from_locked=True` means the provider forces From=username (the frontend should lock the
sender address / default it to the username).
"""

from __future__ import annotations

# id, label, host, port, encryption, from_locked, password_hint, note
_PRESETS: list[dict] = [
    {"id": "qq", "label": "QQ Mail / Foxmail", "host": "smtp.qq.com", "port": 465,
     "encryption": "ssl", "from_locked": True,
     "password_hint": "Authorization code (Settings → Account → Enable SMTP → Generate code, SMS verification required); not the login password"},
    {"id": "163", "label": "163 Mail", "host": "smtp.163.com", "port": 465,
     "encryption": "ssl", "from_locked": True,
     "password_hint": "Authorization code (Settings → POP3/SMTP/IMAP → Enable service, SMS verification required); not the login password"},
    {"id": "126", "label": "126 Mail", "host": "smtp.126.com", "port": 465,
     "encryption": "ssl", "from_locked": True,
     "password_hint": "Authorization code (Settings → POP3/SMTP/IMAP → Enable service); not the login password"},
    {"id": "exmail", "label": "Tencent Business Email", "host": "smtp.exmail.qq.com", "port": 465,
     "encryption": "ssl", "from_locked": True,
     "password_hint": "Login password or client-specific password; the admin must first enable client protocols (IMAP/SMTP) in the admin console"},
    {"id": "aliyun", "label": "Alibaba Business Email", "host": "smtp.qiye.aliyun.com", "port": 465,
     "encryption": "ssl", "from_locked": True,
     "password_hint": "Login password (or the secure password after enabling the client secure password)"},
    {"id": "mobile139", "label": "139 Mail (China Mobile)", "host": "smtp.139.com", "port": 465,
     "encryption": "ssl", "from_locked": True,
     "password_hint": "Client password (Settings → Account & Security → Mailbox protocol settings, set it yourself, SMS verification required)"},
    {"id": "sina", "label": "Sina Mail", "host": "smtp.sina.com", "port": 465,
     "encryption": "ssl", "from_locked": True,
     "password_hint": "Authorization code (enable it in the client POP/IMAP/SMTP settings, SMS verification required)"},
    {"id": "gmail", "label": "Gmail", "host": "smtp.gmail.com", "port": 465,
     "encryption": "ssl", "from_locked": True,
     "password_hint": "App-specific password (enable two-step verification first → generate a 16-digit app password); not the account password"},
    {"id": "outlook", "label": "Outlook / Microsoft 365", "host": "smtp.office365.com", "port": 587,
     "encryption": "starttls", "from_locked": True,
     "password_hint": "Use the password for business accounts (basic authentication will be disabled by default in 2026-12); personal Outlook.com requires OAuth2"},
    {"id": "custom", "label": "Custom SMTP", "host": "", "port": 465,
     "encryption": "auto", "from_locked": False,
     "password_hint": "Fill in according to your provider; for an intranet self-signed certificate you can check \"Allow insecure TLS\""},
]


def all_presets() -> list[dict]:
    return [dict(p) for p in _PRESETS]

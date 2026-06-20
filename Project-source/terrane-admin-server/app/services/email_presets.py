"""邮箱服务商 SMTP 预设（一键填充 host/port/encryption + 凭据提示）。

依据 2026-06 调研核验：国内邮箱几乎都走 465 隐式 SSL（25 端口被云厂商/ISP 普遍封禁），
密码多为「授权码/客户端密码」而非登录密码；From 须=认证账号（163/QQ）。
一份通用 SMTP 实现 + 这些预设即可覆盖：消费邮箱 + 企业邮 + 各大 ESP 的 SMTP 中继。
`from_locked=True` 表示该服务商强制 From=用户名（前端应锁定/默认发件地址=用户名）。
"""

from __future__ import annotations

# id, label, host, port, encryption, from_locked, password_hint, note
_PRESETS: list[dict] = [
    {"id": "qq", "label": "QQ 邮箱 / Foxmail", "host": "smtp.qq.com", "port": 465,
     "encryption": "ssl", "from_locked": True,
     "password_hint": "授权码（设置→账户→开启SMTP→生成授权码，需短信验证）；非登录密码"},
    {"id": "163", "label": "163 邮箱", "host": "smtp.163.com", "port": 465,
     "encryption": "ssl", "from_locked": True,
     "password_hint": "授权码（设置→POP3/SMTP/IMAP→开启服务，需短信验证）；非登录密码"},
    {"id": "126", "label": "126 邮箱", "host": "smtp.126.com", "port": 465,
     "encryption": "ssl", "from_locked": True,
     "password_hint": "授权码（设置→POP3/SMTP/IMAP→开启服务）；非登录密码"},
    {"id": "exmail", "label": "腾讯企业邮箱", "host": "smtp.exmail.qq.com", "port": 465,
     "encryption": "ssl", "from_locked": True,
     "password_hint": "登录密码或客户端专用密码；管理员需先在后台开启客户端协议（IMAP/SMTP）"},
    {"id": "aliyun", "label": "阿里企业邮箱", "host": "smtp.qiye.aliyun.com", "port": 465,
     "encryption": "ssl", "from_locked": True,
     "password_hint": "登录密码（或开启客户端安全密码后用安全密码）"},
    {"id": "mobile139", "label": "139 邮箱（中国移动）", "host": "smtp.139.com", "port": 465,
     "encryption": "ssl", "from_locked": True,
     "password_hint": "客户端密码（设置→账户与安全→邮箱协议设置，自行设置，需短信验证）"},
    {"id": "sina", "label": "新浪邮箱", "host": "smtp.sina.com", "port": 465,
     "encryption": "ssl", "from_locked": True,
     "password_hint": "授权码（客户端 POP/IMAP/SMTP 设置中开启，需短信验证）"},
    {"id": "gmail", "label": "Gmail", "host": "smtp.gmail.com", "port": 465,
     "encryption": "ssl", "from_locked": True,
     "password_hint": "应用专用密码（需先开启两步验证 → 生成 16 位应用密码）；非账号密码"},
    {"id": "outlook", "label": "Outlook / Microsoft 365", "host": "smtp.office365.com", "port": 587,
     "encryption": "starttls", "from_locked": True,
     "password_hint": "企业账户用密码（基础认证将于 2026-12 默认关闭）；个人 Outlook.com 需 OAuth2"},
    {"id": "custom", "label": "自定义 SMTP", "host": "", "port": 465,
     "encryption": "auto", "from_locked": False,
     "password_hint": "按你的服务商填写；内网自签证书可勾选「允许不安全 TLS」"},
]


def all_presets() -> list[dict]:
    return [dict(p) for p in _PRESETS]

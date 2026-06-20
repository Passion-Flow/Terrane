"""TOTP（RFC 6238,SHA1/30s/6 位)—— 零依赖自实现。2FA 用。

secret 以 base32 存储(库内再经 KEK 加密)。verify 默认 ±1 时间窗容时钟漂移。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from urllib.parse import quote


def gen_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")


def _code_at(secret_b32: str, ts: float, step: int = 30, digits: int = 6) -> str:
    pad = "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(secret_b32.upper() + pad)
    counter = int(ts // step)
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    val = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(val).zfill(digits)


def now_code(secret_b32: str) -> str:
    return _code_at(secret_b32, time.time())


def verify(secret_b32: str, code: str, window: int = 1) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit():
        return False
    t = time.time()
    return any(hmac.compare_digest(_code_at(secret_b32, t + i * 30), code)
               for i in range(-window, window + 1))


def provisioning_uri(secret_b32: str, account: str, issuer: str = "Terrane") -> str:
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret_b32}"
            f"&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30")


def gen_backup_codes(n: int = 10) -> list[str]:
    return [base64.b32encode(os.urandom(5)).decode("ascii").rstrip("=").lower() for _ in range(n)]

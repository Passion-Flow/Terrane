"""KEK 字段级加密（L5 敏感:SMTP 密码 / 2FA 秘钥 / 连接器凭据）。

Fernet(AES-128-CBC + HMAC)。KEK 来源:环境 TERRANE_KEK(Fernet key 或任意串派生),
缺省走稳定 dev 派生(重启可解密;**生产必须设 TERRANE_KEK**)。密文带 `enc:v1:` 前缀,
兼容历史明文(decrypt 遇非密文原样返回)。
"""

from __future__ import annotations

import base64
import functools
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "enc:v1:"


@functools.lru_cache(maxsize=1)
def _fernet() -> Fernet:
    raw = os.getenv("TERRANE_KEK", "").strip()
    if raw:
        try:
            return Fernet(raw.encode())          # 已是合法 Fernet key
        except (ValueError, Exception):          # noqa: BLE001 — 任意串派生 32 字节
            key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
            return Fernet(key)
    # dev 缺省(稳定派生,非生产)
    key = base64.urlsafe_b64encode(hashlib.sha256(b"terrane-dev-kek-v1").digest())
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return plaintext
    return _PREFIX + _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str | None) -> str:
    if not token or not token.startswith(_PREFIX):
        return token or ""        # 兼容历史明文
    try:
        return _fernet().decrypt(token[len(_PREFIX):].encode()).decode()
    except InvalidToken:
        return ""                 # KEK 变更/损坏 → 视为空,不崩


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(_PREFIX)

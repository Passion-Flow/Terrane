"""KEK field-level encryption (L5 sensitive: SMTP passwords / 2FA secrets / connector credentials).

Fernet (AES-128-CBC + HMAC). The KEK comes from the TERRANE_KEK environment variable (a Fernet key,
or derived from any string); it defaults to a stable dev derivation (decryptable across restarts;
**production MUST set TERRANE_KEK**). Ciphertext carries the `enc:v1:` prefix and is backward-compatible
with legacy plaintext (decrypt returns non-ciphertext as-is).
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
            return Fernet(raw.encode())          # already a valid Fernet key
        except (ValueError, Exception):          # noqa: BLE001 — derive 32 bytes from an arbitrary string
            key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
            return Fernet(key)
    # dev default (stable derivation, not for production)
    key = base64.urlsafe_b64encode(hashlib.sha256(b"terrane-dev-kek-v1").digest())
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return plaintext
    return _PREFIX + _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str | None) -> str:
    if not token or not token.startswith(_PREFIX):
        return token or ""        # backward-compatible with legacy plaintext
    try:
        return _fernet().decrypt(token[len(_PREFIX):].encode()).decode()
    except InvalidToken:
        return ""                 # KEK changed/corrupted -> treat as empty, do not crash


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(_PREFIX)

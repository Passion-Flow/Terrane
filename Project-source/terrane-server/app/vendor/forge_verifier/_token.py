"""Compact signed-token codec — MUST match forge-server app/licensing/forge_file.py.

Format: <base64url(canonical_payload_json)>.<base64url(ed25519_signature)>
"""

from __future__ import annotations

import base64
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key


def b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def canonical_payload_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def parse_and_verify(blob: str, public_pem: bytes) -> tuple[bool, dict]:
    """Return (signature_valid, payload). Verifies the detached Ed25519 signature over the
    EXACT payload bytes with the embedded public key."""
    parts = blob.strip().split(".")
    if len(parts) != 2:
        raise ValueError("malformed token")
    payload_bytes = b64u_decode(parts[0])
    signature = b64u_decode(parts[1])
    payload = json.loads(payload_bytes)
    pub = load_pem_public_key(public_pem)
    if not isinstance(pub, Ed25519PublicKey):
        raise ValueError("embedded key is not Ed25519")
    try:
        pub.verify(signature, payload_bytes)
        return True, payload
    except Exception:
        return False, payload

"""Embedded vendor public keys.

In a real consumer product these are COMPILED IN (constants shipped with the product), never
configured by the customer (licensing.md). For development/integration the vendor populates
`embedded_keys.json` next to this file at SDK build time via `forge keys export-public`.
"""

from __future__ import annotations

import json
import os
import pathlib

_PATH = pathlib.Path(__file__).with_name("embedded_keys.json")


def _load() -> dict:
    # SECURITY: the env override is honored ONLY when FORGE_SDK_DEV is set (tests/integration).
    # In a shipped product it is IGNORED — otherwise an attacker could set FORGE_EMBEDDED_KEYS to
    # their OWN public key and present a self-signed license. The verification key must be
    # unswappable. (Ideally bake the PEM as a source constant; the JSON file is a build convenience.)
    if os.environ.get("FORGE_SDK_DEV") and (env := os.environ.get("FORGE_EMBEDDED_KEYS")):
        return json.loads(env)
    if _PATH.is_file():
        return json.loads(_PATH.read_text(encoding="utf-8"))
    raise RuntimeError("embedded_keys.json missing — bake in vendor public keys at SDK build")


def master_public_pem() -> bytes:
    return _load()["master"]["public_key"].encode("utf-8")


def edge_lease_public_pem() -> bytes:
    return _load()["edge_lease"]["public_key"].encode("utf-8")

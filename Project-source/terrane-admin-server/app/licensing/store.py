"""Activation envelope persistence — the admin backend is the sole writer; server/gateway only read the same shared volume."""

from __future__ import annotations

import json
import os
from pathlib import Path


def write_envelope(path: Path, method: str, credential: str) -> None:
    """Atomically write the activation envelope (write a temp file + rename, so readers never read a partial file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"method": method, "credential": credential}, ensure_ascii=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)

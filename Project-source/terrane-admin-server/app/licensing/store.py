"""激活信封持久化 — 后台是唯一写入方；server/gateway 只读同一共享卷。"""

from __future__ import annotations

import json
import os
from pathlib import Path


def write_envelope(path: Path, method: str, credential: str) -> None:
    """原子写入激活信封（写临时文件 + rename，避免读端读到半截）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"method": method, "credential": credential}, ensure_ascii=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)

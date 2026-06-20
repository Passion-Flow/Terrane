"""标识符工具 — UUID v7 主键（时序友好，照搬 Forge app/core/ids.py）。"""

from __future__ import annotations

import uuid

import uuid_utils


def uuid7() -> uuid.UUID:
    """业务主键用的时序 UUID v7。"""
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)


def new_request_id() -> str:
    return f"req_{uuid_utils.uuid7().hex[:24]}"

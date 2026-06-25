"""Identifier helpers — UUID v7 primary keys (time-ordered, ported from Forge app/core/ids.py)."""

from __future__ import annotations

import uuid

import uuid_utils


def uuid7() -> uuid.UUID:
    """Time-ordered UUID v7 used as a business primary key."""
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)


def new_request_id() -> str:
    return f"req_{uuid_utils.uuid7().hex[:24]}"

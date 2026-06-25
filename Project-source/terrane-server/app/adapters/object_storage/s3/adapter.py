"""AWS S3 (also serves any generic S3-compatible endpoint specified via object_storage_endpoint)."""

from __future__ import annotations

from app.adapters.object_storage.base import S3CompatibleStorage


class S3Storage(S3CompatibleStorage):
    addressing_style = "virtual"

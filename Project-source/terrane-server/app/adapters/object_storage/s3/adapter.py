"""AWS S3（也服务于任意通过 object_storage_endpoint 指定的通用 S3 兼容端点）。"""

from __future__ import annotations

from app.adapters.object_storage.base import S3CompatibleStorage


class S3Storage(S3CompatibleStorage):
    addressing_style = "virtual"

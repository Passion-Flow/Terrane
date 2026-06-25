"""Tencent COS via its S3-compatible endpoint (cos.<region>.myqcloud.com).

Note: COS bucket names are "<name>-<appid>" -- set that full value as the bucket.
"""

from __future__ import annotations

from app.adapters.object_storage.base import S3CompatibleStorage


class TencentCOSStorage(S3CompatibleStorage):
    addressing_style = "virtual"

    def endpoint_url(self) -> str | None:
        if self.settings.object_storage_endpoint:
            return self.settings.object_storage_endpoint
        region = self.settings.object_storage_region or "ap-guangzhou"
        scheme = "https" if self.settings.object_storage_secure else "http"
        return f"{scheme}://cos.{region}.myqcloud.com"

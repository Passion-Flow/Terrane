"""阿里云 OSS 经其 S3 兼容端点（oss-<region>.aliyuncs.com）。"""

from __future__ import annotations

from app.adapters.object_storage.base import S3CompatibleStorage


class AliyunOSSStorage(S3CompatibleStorage):
    addressing_style = "virtual"

    def endpoint_url(self) -> str | None:
        if self.settings.object_storage_endpoint:
            return self.settings.object_storage_endpoint
        region = self.settings.object_storage_region or "oss-cn-hangzhou"
        scheme = "https" if self.settings.object_storage_secure else "http"
        return f"{scheme}://{region}.aliyuncs.com"

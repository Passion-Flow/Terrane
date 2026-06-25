"""Volcengine TOS via its S3-compatible endpoint (tos-s3-<region>.volces.com)."""

from __future__ import annotations

from app.adapters.object_storage.base import S3CompatibleStorage


class VolcengineTOSStorage(S3CompatibleStorage):
    addressing_style = "virtual"

    def endpoint_url(self) -> str | None:
        if self.settings.object_storage_endpoint:
            return self.settings.object_storage_endpoint
        region = self.settings.object_storage_region or "cn-beijing"
        scheme = "https" if self.settings.object_storage_secure else "http"
        return f"{scheme}://tos-s3-{region}.volces.com"

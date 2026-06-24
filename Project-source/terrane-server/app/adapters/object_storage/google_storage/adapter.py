"""Google Cloud Storage（原生 google-cloud-storage SDK）。Bucket == bucket。"""

from __future__ import annotations

import asyncio
import datetime

from app.adapters.object_storage.base import ObjectStat, ObjectStorageAdapter


class GoogleCloudStorage(ObjectStorageAdapter):
    def _client(self):
        from google.cloud import storage  # 惰性 import

        project = self.settings.object_storage_gcs_project or None
        # 自定义端点 = GCS 模拟器（fake-gcs-server）或私有 Google API 端点。
        if self.settings.object_storage_endpoint:
            from google.auth.credentials import AnonymousCredentials
            return storage.Client(
                project=project or "terrane",
                credentials=AnonymousCredentials(),
                client_options={"api_endpoint": self.settings.object_storage_endpoint},
            )
        cred = self.settings.object_storage_gcs_credentials_json
        if cred:
            return storage.Client.from_service_account_json(cred, project=project)
        return storage.Client(project=project)

    def _blob(self, key: str, bucket: str | None):
        return self._client().bucket(self._bucket(bucket)).blob(key)

    def _expires(self, expires: int | None) -> int:
        return expires or self.settings.object_storage_presigned_url_expires

    async def upload(self, key, data, *, bucket=None, content_type=None, public=False):
        def _do():
            b = self._blob(key, bucket)
            b.upload_from_string(data, content_type=content_type or "application/octet-stream")
            if public:
                b.make_public()
            return ObjectStat(key=key, size=len(data), content_type=content_type)
        return await asyncio.to_thread(_do)

    async def download(self, key, *, bucket=None):
        return await asyncio.to_thread(lambda: self._blob(key, bucket).download_as_bytes())

    async def delete(self, key, *, bucket=None):
        def _do():
            try:
                self._blob(key, bucket).delete()
            except Exception:
                pass
        await asyncio.to_thread(_do)

    async def head(self, key, *, bucket=None):
        def _do():
            b = self._blob(key, bucket)
            if not b.exists():
                return None
            b.reload()
            return ObjectStat(key=key, size=b.size or 0, etag=b.etag, content_type=b.content_type,
                              last_modified=str(b.updated) if b.updated else None)
        return await asyncio.to_thread(_do)

    async def list(self, prefix="", *, bucket=None):
        def _do():
            client = self._client()
            return [ObjectStat(key=b.name, size=b.size or 0)
                    for b in client.list_blobs(self._bucket(bucket), prefix=prefix)]
        return await asyncio.to_thread(_do)

    async def presigned_upload_url(self, key, *, bucket=None, expires=None, content_type=None):
        def _do():
            return self._blob(key, bucket).generate_signed_url(
                version="v4", method="PUT",
                expiration=datetime.timedelta(seconds=self._expires(expires)),
                content_type=content_type)
        return await asyncio.to_thread(_do)

    async def presigned_download_url(self, key, *, bucket=None, expires=None):
        def _do():
            return self._blob(key, bucket).generate_signed_url(
                version="v4", method="GET",
                expiration=datetime.timedelta(seconds=self._expires(expires)))
        return await asyncio.to_thread(_do)

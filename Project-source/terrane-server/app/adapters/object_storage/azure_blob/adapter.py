"""Azure Blob Storage (native azure-storage-blob SDK). Container == bucket."""

from __future__ import annotations

import asyncio
import datetime

from app.adapters.object_storage.base import ObjectStat, ObjectStorageAdapter


class AzureBlobStorage(ObjectStorageAdapter):
    def _account_url(self) -> str:
        # A custom endpoint supports Azurite (emulator) / Azure Stack / sovereign clouds;
        # this endpoint already includes the account path
        # (e.g. http://azurite:10000/devstoreaccount1).
        if self.settings.object_storage_endpoint:
            return self.settings.object_storage_endpoint.rstrip("/")
        scheme = "https" if self.settings.object_storage_secure else "http"
        return f"{scheme}://{self.settings.object_storage_azure_account}.blob.core.windows.net"

    def _service(self):
        from azure.storage.blob import BlobServiceClient  # lazy import
        # The dict credential carries the account name explicitly -- required when the
        # account cannot be inferred from the custom endpoint host (Azurite / Azure Stack).
        cred = {"account_name": self.settings.object_storage_azure_account,
                "account_key": self.settings.object_storage_azure_key}
        return BlobServiceClient(account_url=self._account_url(), credential=cred)

    def _blob(self, key: str, bucket: str | None):
        return self._service().get_blob_client(container=self._bucket(bucket), blob=key)

    def _expires(self, expires: int | None) -> int:
        return expires or self.settings.object_storage_presigned_url_expires

    async def upload(self, key, data, *, bucket=None, content_type=None, public=False):
        def _do():
            from azure.storage.blob import ContentSettings
            cs = ContentSettings(content_type=content_type) if content_type else None
            self._blob(key, bucket).upload_blob(data, overwrite=True, content_settings=cs)
            return ObjectStat(key=key, size=len(data), content_type=content_type)
        return await asyncio.to_thread(_do)

    async def download(self, key, *, bucket=None):
        return await asyncio.to_thread(lambda: self._blob(key, bucket).download_blob().readall())

    async def delete(self, key, *, bucket=None):
        def _do():
            try:
                self._blob(key, bucket).delete_blob()
            except Exception:
                pass
        await asyncio.to_thread(_do)

    async def head(self, key, *, bucket=None):
        def _do():
            b = self._blob(key, bucket)
            if not b.exists():
                return None
            p = b.get_blob_properties()
            return ObjectStat(key=key, size=p.size, etag=p.etag,
                              content_type=p.content_settings.content_type,
                              last_modified=str(p.last_modified) if p.last_modified else None)
        return await asyncio.to_thread(_do)

    async def list(self, prefix="", *, bucket=None):
        def _do():
            cc = self._service().get_container_client(self._bucket(bucket))
            return [ObjectStat(key=b.name, size=b.size or 0) for b in cc.list_blobs(name_starts_with=prefix)]
        return await asyncio.to_thread(_do)

    def _sas(self, key: str, bucket: str | None, expires: int | None, write: bool) -> str:
        from azure.storage.blob import BlobSasPermissions, generate_blob_sas
        container = self._bucket(bucket)
        token = generate_blob_sas(
            account_name=self.settings.object_storage_azure_account,
            container_name=container, blob_name=key,
            account_key=self.settings.object_storage_azure_key,
            permission=BlobSasPermissions(write=True, create=True) if write else BlobSasPermissions(read=True),
            expiry=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=self._expires(expires)),
        )
        return f"{self._account_url()}/{container}/{key}?{token}"

    async def presigned_upload_url(self, key, *, bucket=None, expires=None, content_type=None):
        return await asyncio.to_thread(lambda: self._sas(key, bucket, expires, write=True))

    async def presigned_download_url(self, key, *, bucket=None, expires=None):
        return await asyncio.to_thread(lambda: self._sas(key, bucket, expires, write=False))

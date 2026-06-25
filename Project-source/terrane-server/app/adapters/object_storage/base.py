"""Object storage adapter interface -- business code does not depend on any SDK
directly; each provider implements this interface (all-provider rule: all 8
providers must ship an adapter).

Unified surface: upload / download / delete / head / list / presigned_upload_url /
presigned_download_url. The provider is selected at startup by object_storage_type.

Most providers (AWS S3, local SeaweedFS, Aliyun OSS, Tencent COS, Volcengine TOS,
Huawei OBS) expose an S3-compatible API, so they share `S3CompatibleStorage`
(boto3) and differ only in endpoint/region. Azure Blob and Google Cloud Storage
use their own native SDKs.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.config import Settings


@dataclass
class ObjectStat:
    key: str
    size: int
    etag: str | None = None
    content_type: str | None = None
    last_modified: str | None = None


class ObjectStorageAdapter(ABC):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def default_bucket(self) -> str:
        return self.settings.object_storage_default_bucket

    def _bucket(self, bucket: str | None) -> str:
        return bucket or self.default_bucket

    @abstractmethod
    async def upload(self, key: str, data: bytes, *, bucket: str | None = None,
                     content_type: str | None = None, public: bool = False) -> ObjectStat: ...

    @abstractmethod
    async def download(self, key: str, *, bucket: str | None = None) -> bytes: ...

    @abstractmethod
    async def delete(self, key: str, *, bucket: str | None = None) -> None: ...

    @abstractmethod
    async def head(self, key: str, *, bucket: str | None = None) -> ObjectStat | None: ...

    @abstractmethod
    async def list(self, prefix: str = "", *, bucket: str | None = None) -> list[ObjectStat]: ...

    @abstractmethod
    async def presigned_upload_url(self, key: str, *, bucket: str | None = None,
                                   expires: int | None = None, content_type: str | None = None) -> str: ...

    @abstractmethod
    async def presigned_download_url(self, key: str, *, bucket: str | None = None,
                                     expires: int | None = None) -> str: ...

    async def ensure_bucket(self, bucket: str | None = None) -> None:
        """Idempotently ensure the bucket exists. No-op by default (for providers
        without a bucket concept, e.g. filesystem)."""
        return None

    async def health_check(self) -> bool:
        try:
            await self.list(prefix="__health__/")
            return True
        except Exception:
            return False


class S3CompatibleStorage(ObjectStorageAdapter):
    """boto3-based adapter for any S3-compatible endpoint (AWS S3, SeaweedFS, OSS,
    COS, TOS, OBS).

    Subclasses override `endpoint_url()` / `region()` to inject provider defaults;
    all blocking boto3 calls are offloaded to a thread via asyncio.to_thread to
    honor the async contract.
    """

    # Some S3-compatible vendors require a non-AWS addressing style; subclasses adjust as needed.
    addressing_style = "auto"

    def endpoint_url(self) -> str | None:
        return self.settings.object_storage_endpoint or None

    def region(self) -> str | None:
        return self.settings.object_storage_region or None

    def _client(self):
        # Lazy import: boto3 is only needed when an S3-compatible provider is selected.
        import boto3
        from botocore.config import Config

        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url(),
            region_name=self.region(),
            aws_access_key_id=self.settings.object_storage_access_key or None,
            aws_secret_access_key=self.settings.object_storage_secret_key or None,
            use_ssl=self.settings.object_storage_secure,
            config=Config(signature_version="s3v4", s3={"addressing_style": self.addressing_style}),
        )

    def _expires(self, expires: int | None) -> int:
        return expires or self.settings.object_storage_presigned_url_expires

    async def ensure_bucket(self, bucket=None):
        def _do():
            from botocore.exceptions import ClientError
            c = self._client()
            b = self._bucket(bucket)
            try:
                c.head_bucket(Bucket=b)
                return
            except ClientError:
                pass
            try:
                c.create_bucket(Bucket=b)
            except ClientError:
                pass  # already exists / concurrent creation / no permission (cloud buckets are usually pre-provisioned) -> ignore
        await asyncio.to_thread(_do)

    async def upload(self, key, data, *, bucket=None, content_type=None, public=False):
        def _do():
            c = self._client()
            extra = {}
            if content_type:
                extra["ContentType"] = content_type
            if public:
                extra["ACL"] = "public-read"
            c.put_object(Bucket=self._bucket(bucket), Key=key, Body=data, **extra)
            return ObjectStat(key=key, size=len(data), content_type=content_type)
        return await asyncio.to_thread(_do)

    async def download(self, key, *, bucket=None):
        def _do():
            c = self._client()
            obj = c.get_object(Bucket=self._bucket(bucket), Key=key)
            return obj["Body"].read()
        return await asyncio.to_thread(_do)

    async def delete(self, key, *, bucket=None):
        def _do():
            self._client().delete_object(Bucket=self._bucket(bucket), Key=key)
        await asyncio.to_thread(_do)

    async def head(self, key, *, bucket=None):
        def _do():
            from botocore.exceptions import ClientError
            try:
                r = self._client().head_object(Bucket=self._bucket(bucket), Key=key)
            except ClientError:
                return None
            return ObjectStat(key=key, size=r.get("ContentLength", 0), etag=r.get("ETag"),
                              content_type=r.get("ContentType"),
                              last_modified=str(r.get("LastModified")) if r.get("LastModified") else None)
        return await asyncio.to_thread(_do)

    async def list(self, prefix="", *, bucket=None):
        def _do():
            c = self._client()
            out: list[ObjectStat] = []
            token = None
            while True:
                kw = {"Bucket": self._bucket(bucket), "Prefix": prefix}
                if token:
                    kw["ContinuationToken"] = token
                r = c.list_objects_v2(**kw)
                for o in r.get("Contents", []):
                    out.append(ObjectStat(key=o["Key"], size=o.get("Size", 0), etag=o.get("ETag"),
                                          last_modified=str(o.get("LastModified")) if o.get("LastModified") else None))
                if not r.get("IsTruncated"):
                    break
                token = r.get("NextContinuationToken")
            return out
        return await asyncio.to_thread(_do)

    async def presigned_upload_url(self, key, *, bucket=None, expires=None, content_type=None):
        def _do():
            params = {"Bucket": self._bucket(bucket), "Key": key}
            if content_type:
                params["ContentType"] = content_type
            return self._client().generate_presigned_url(
                "put_object", Params=params, ExpiresIn=self._expires(expires))
        return await asyncio.to_thread(_do)

    async def presigned_download_url(self, key, *, bucket=None, expires=None):
        def _do():
            return self._client().generate_presigned_url(
                "get_object", Params={"Bucket": self._bucket(bucket), "Key": key},
                ExpiresIn=self._expires(expires))
        return await asyncio.to_thread(_do)


def get_object_storage_adapter(settings: Settings) -> ObjectStorageAdapter:
    t = settings.object_storage_type
    if t == "local":
        from app.adapters.object_storage.local.adapter import LocalStorage
        return LocalStorage(settings)
    if t == "s3":
        from app.adapters.object_storage.s3.adapter import S3Storage
        return S3Storage(settings)
    if t == "azure-blob":
        from app.adapters.object_storage.azure_blob.adapter import AzureBlobStorage
        return AzureBlobStorage(settings)
    if t == "aliyun-oss":
        from app.adapters.object_storage.aliyun_oss.adapter import AliyunOSSStorage
        return AliyunOSSStorage(settings)
    if t == "google-storage":
        from app.adapters.object_storage.google_storage.adapter import GoogleCloudStorage
        return GoogleCloudStorage(settings)
    if t == "tencent-cos":
        from app.adapters.object_storage.tencent_cos.adapter import TencentCOSStorage
        return TencentCOSStorage(settings)
    if t == "volcengine-tos":
        from app.adapters.object_storage.volcengine_tos.adapter import VolcengineTOSStorage
        return VolcengineTOSStorage(settings)
    if t == "huawei-obs":
        from app.adapters.object_storage.huawei_obs.adapter import HuaweiOBSStorage
        return HuaweiOBSStorage(settings)
    raise ValueError(f"unknown object_storage_type: {t}")

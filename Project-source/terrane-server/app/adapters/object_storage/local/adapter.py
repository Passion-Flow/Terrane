"""本地对象存储 —— 双模：
- filesystem：在 object_storage_local_path/<bucket>/<key> 下的纯磁盘存储（开发默认）；
- s3：委托给 S3 兼容客户端，指向本地 SeaweedFS 端点（自托管默认）。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from app.adapters.object_storage.base import ObjectStat, ObjectStorageAdapter, S3CompatibleStorage
from app.core.config import Settings


class LocalStorage(ObjectStorageAdapter):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._remote: S3CompatibleStorage | None = None
        if settings.object_storage_local_mode != "filesystem":
            # 非 filesystem 模式 = 委托给 SeaweedFS（S3 兼容，端点取 object_storage_endpoint）。
            self._remote = S3CompatibleStorage(settings)

    async def ensure_bucket(self, bucket=None):
        if self._remote:
            return await self._remote.ensure_bucket(bucket)
        return None  # filesystem 模式无 bucket 概念，upload 时按需 mkdir

    def _root(self, bucket: str | None) -> Path:
        return Path(self.settings.object_storage_local_path) / self._bucket(bucket)

    def _path(self, key: str, bucket: str | None) -> Path:
        return self._root(bucket) / key

    async def upload(self, key, data, *, bucket=None, content_type=None, public=False):
        if self._remote:
            return await self._remote.upload(key, data, bucket=bucket, content_type=content_type, public=public)

        def _do():
            p = self._path(key, bucket)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            return ObjectStat(key=key, size=len(data), content_type=content_type)
        return await asyncio.to_thread(_do)

    async def download(self, key, *, bucket=None):
        if self._remote:
            return await self._remote.download(key, bucket=bucket)
        return await asyncio.to_thread(lambda: self._path(key, bucket).read_bytes())

    async def delete(self, key, *, bucket=None):
        if self._remote:
            return await self._remote.delete(key, bucket=bucket)

        def _do():
            try:
                self._path(key, bucket).unlink()
            except FileNotFoundError:
                pass
        await asyncio.to_thread(_do)

    async def head(self, key, *, bucket=None):
        if self._remote:
            return await self._remote.head(key, bucket=bucket)

        def _do():
            p = self._path(key, bucket)
            if not p.exists():
                return None
            st = p.stat()
            return ObjectStat(key=key, size=st.st_size, last_modified=str(int(st.st_mtime)))
        return await asyncio.to_thread(_do)

    async def list(self, prefix="", *, bucket=None):
        if self._remote:
            return await self._remote.list(prefix, bucket=bucket)

        def _do():
            root = self._root(bucket)
            if not root.exists():
                return []
            out: list[ObjectStat] = []
            for dirpath, _dirs, files in os.walk(root):
                for f in files:
                    full = Path(dirpath) / f
                    rel = str(full.relative_to(root))
                    if rel.startswith(prefix):
                        out.append(ObjectStat(key=rel, size=full.stat().st_size))
            return out
        return await asyncio.to_thread(_do)

    async def presigned_upload_url(self, key, *, bucket=None, expires=None, content_type=None):
        if self._remote:
            return await self._remote.presigned_upload_url(key, bucket=bucket, expires=expires, content_type=content_type)
        # 文件系统模式无预签名；这些路径由应用内部提供服务。
        return f"/internal/storage/{self._bucket(bucket)}/{key}"

    async def presigned_download_url(self, key, *, bucket=None, expires=None):
        if self._remote:
            return await self._remote.presigned_download_url(key, bucket=bucket, expires=expires)
        return f"/internal/storage/{self._bucket(bucket)}/{key}"

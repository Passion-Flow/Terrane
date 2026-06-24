"""对象存储使用层 —— 原文件 + 逐页 WebP 页面图的 key 约定 + 适配器单例。

provider 由 object_storage_type 选定（8 选 1，见 app/adapters/object_storage）。出厂自托管默认
SeaweedFS（local 双模 s3）。本模块只暴露应用语义（原文/页面图 key），不感知具体 provider。
"""

from __future__ import annotations

import uuid

from app.adapters.object_storage import ObjectStorageAdapter, get_object_storage_adapter
from app.core.config import get_settings

_adapter: ObjectStorageAdapter | None = None


_bucket_ready = False


def get_adapter() -> ObjectStorageAdapter:
    """进程内单例适配器（按 object_storage_type 实例化一次）。"""
    global _adapter
    if _adapter is None:
        _adapter = get_object_storage_adapter(get_settings())
    return _adapter


async def ensure_bucket() -> None:
    """首次写入前幂等确保默认 bucket 存在（SeaweedFS/自托管首启）。进程内只跑一次。"""
    global _bucket_ready
    if _bucket_ready:
        return
    try:
        await get_adapter().ensure_bucket()
    except Exception:  # noqa: BLE001
        pass
    _bucket_ready = True


def original_key(raw_source_id: uuid.UUID | str) -> str:
    """原始上传文件对象 key。"""
    return f"originals/{raw_source_id}"


def page_key(raw_source_id: uuid.UUID | str, page_no: int) -> str:
    """第 page_no 页（1-based）的 WebP 版面图 key。"""
    return f"pages/{raw_source_id}/{page_no}.webp"


async def delete_source_objects(raw_source_id: uuid.UUID | str) -> None:
    """删除某源在对象存储里的全部对象（原文 + 所有页面图）。best-effort，不抛。"""
    a = get_adapter()
    try:
        await a.delete(original_key(raw_source_id))
    except Exception:  # noqa: BLE001
        pass
    try:
        for o in await a.list(f"pages/{raw_source_id}/"):
            try:
                await a.delete(o.key)
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass

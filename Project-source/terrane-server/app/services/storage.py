"""Object storage usage layer -- key conventions for the original file plus per-page WebP page images, and the adapter singleton.

The provider is chosen by object_storage_type (1 of 8, see app/adapters/object_storage). The self-hosted
factory default is SeaweedFS (local dual-mode s3). This module exposes only application semantics
(original / page-image keys) and is agnostic to the concrete provider.
"""

from __future__ import annotations

import uuid

from app.adapters.object_storage import ObjectStorageAdapter, get_object_storage_adapter
from app.core.config import get_settings

_adapter: ObjectStorageAdapter | None = None


_bucket_ready = False


def get_adapter() -> ObjectStorageAdapter:
    """In-process singleton adapter (instantiated once per object_storage_type)."""
    global _adapter
    if _adapter is None:
        _adapter = get_object_storage_adapter(get_settings())
    return _adapter


async def ensure_bucket() -> None:
    """Idempotently ensure the default bucket exists before the first write (SeaweedFS / self-hosted first start). Runs only once per process."""
    global _bucket_ready
    if _bucket_ready:
        return
    try:
        await get_adapter().ensure_bucket()
    except Exception:  # noqa: BLE001
        pass
    _bucket_ready = True


def original_key(raw_source_id: uuid.UUID | str) -> str:
    """Object key for the originally uploaded file."""
    return f"originals/{raw_source_id}"


def page_key(raw_source_id: uuid.UUID | str, page_no: int) -> str:
    """Object key for the WebP layout image of page page_no (1-based)."""
    return f"pages/{raw_source_id}/{page_no}.webp"


def figure_key(raw_source_id: uuid.UUID | str, page_no: int, idx: int) -> str:
    """Object key for the WebP crop of figure `idx` (0-based, in reading order) on page `page_no` (1-based).

    Parallels `page_key`: a figure crop is served the same way as a page image (same adapter, same
    immutable-WebP serving route), so a `![caption](.../figure/{page}/{idx})` reference resolves to the stored
    crop. The crop is the topology/artwork itself (kept as an IMAGE, never serialized to false connections)."""
    return f"figures/{raw_source_id}/{page_no}-{idx}.webp"


def video_frame_key(raw_source_id: uuid.UUID | str, idx: int) -> str:
    """Object key for keyframe `idx` (0-based, in time order) extracted from a video source.

    Served the same way as a page/figure image (same adapter, same immutable-image route), so a
    `![帧](.../video-frame/{idx})` reference in the timecoded Markdown resolves to the stored keyframe and a
    retrieval hit can deep-link to its scene."""
    return f"video/{raw_source_id}/{idx}.jpg"


async def delete_source_objects(raw_source_id: uuid.UUID | str) -> None:
    """Delete all objects for a source in object storage (original + all page images). Best-effort, never raises."""
    a = get_adapter()
    try:
        await a.delete(original_key(raw_source_id))
    except Exception:  # noqa: BLE001
        pass
    for prefix in (f"pages/{raw_source_id}/", f"figures/{raw_source_id}/", f"video/{raw_source_id}/"):
        try:
            for o in await a.list(prefix):
                try:
                    await a.delete(o.key)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass

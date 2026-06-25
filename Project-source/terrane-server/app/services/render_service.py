"""Page-by-page WebP layout rendering pipeline for original documents.

PDF -> PyMuPDF rasterizes each page -> WebP; Office (docx/xlsx/pptx and legacy doc/xls/ppt) -> LibreOffice headless
conversion to PDF -> same as above. Page images go to object storage (pages/{rid}/{n}.webp); page count + per-page dimensions go to raw_source_renders.
Runs asynchronously in the background; failures are only logged and do not affect ingestion/retrieval/Q&A (object-storage degradation rule).

The front end uses the pages dimensions in raw_source_renders for placeholders and lazy-loads individual WebP pages by viewport — large-file previews no longer download the whole file.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import uuid

import structlog
from sqlalchemy import update

from app.db.session import get_sessionmaker
from app.models.kb_content import RawSourceRender
from app.services import storage

log = structlog.get_logger("terrane.render")

DPI = 130                # 144 is HD-quality but heavier; 130 balances clarity and size
WEBP_QUALITY = 80
WEBP_METHOD = 4          # Pillow WebP compression effort, 0 (fast) - 6 (small)
MAX_PAGES = 1000         # Per-file page cap (prevents oversized PDFs from overwhelming rendering/storage)
PROGRESS_BATCH = 8       # Progressive rendering: update status every N pages so the front end can view as it renders
_SOFFICE_TIMEOUT = 180

PDF_MIME = "application/pdf"
OFFICE_MIMES: dict[str, str] = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/msword": ".doc",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.ms-powerpoint": ".ppt",
}
RENDER_MIMES = {PDF_MIME, *OFFICE_MIMES}

# LibreOffice is single-instance/single-threaded; concurrent conversions silently produce empty files -> serialize across the whole process (conclusion from the 03-Services / Web research).
_LO_LOCK = asyncio.Lock()


def renderable(mime: str | None) -> bool:
    return bool(mime) and mime in RENDER_MIMES


def _soffice_to_pdf(data: bytes, ext: str) -> bytes | None:
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, f"in{ext}")
        with open(src, "wb") as f:
            f.write(data)
        profile = os.path.join(d, "lo_profile")  # A separate UserInstallation each time, to avoid profile locks between instances
        try:
            subprocess.run(
                ["soffice", "--headless", "--norestore", "--nolockcheck", "--nodefault",
                 f"-env:UserInstallation=file://{profile}",
                 "--convert-to", "pdf", "--outdir", d, src],
                check=True, timeout=_SOFFICE_TIMEOUT,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            log.warning("soffice_failed", error=str(e))
            return None
        out = os.path.join(d, "in.pdf")
        if os.path.exists(out):
            with open(out, "rb") as f:
                return f.read()
        return None


def _pdf_page_count(pdf_bytes: bytes) -> int:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return min(doc.page_count, MAX_PAGES)
    finally:
        doc.close()


def _render_batch(pdf_bytes: bytes, start: int, count: int) -> list[tuple[int, int, int, bytes]]:
    """Render pages in the range [start, start+count) -> [(page number 1-based, w, h, webp), ...]."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out: list[tuple[int, int, int, bytes]] = []
    try:
        end = min(start + count, doc.page_count, MAX_PAGES)
        for i in range(start, end):
            pix = doc[i].get_pixmap(dpi=DPI)
            webp = pix.pil_tobytes(format="WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
            out.append((i + 1, pix.width, pix.height, webp))
    finally:
        doc.close()
    return out


def render_one_page(pdf_bytes: bytes, page_no: int) -> tuple[int, int, bytes] | None:
    """Render a single page on demand (1-based) -> (w, h, webp). Used by the "render-as-you-scroll" endpoint for large documents."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if page_no < 1 or page_no > doc.page_count:
            return None
        pix = doc[page_no - 1].get_pixmap(dpi=DPI)
        return pix.width, pix.height, pix.pil_tobytes(format="WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
    finally:
        doc.close()


async def to_pdf(data: bytes, mime: str, ext: str) -> bytes | None:
    """Original document -> PDF bytes. PDF is returned directly; Office is converted via LibreOffice (serialized); anything else is non-renderable and returns None."""
    if mime == PDF_MIME:
        return data
    if mime in OFFICE_MIMES:
        async with _LO_LOCK:
            return await asyncio.to_thread(_soffice_to_pdf, data, OFFICE_MIMES.get(mime) or ext)
    return None


async def _set_status(db, rid: uuid.UUID, **values) -> None:
    await db.execute(update(RawSourceRender).where(RawSourceRender.raw_source_id == rid).values(**values))
    await db.commit()


async def render_source_bg(raw_source_id: uuid.UUID, data: bytes, mime: str, ext: str) -> None:
    """Background **progressive** rendering: original document -> PDF -> batched page-by-page WebP -> object storage; status is updated once per batch,
    so the front end can view as it renders (the first batch appears instantly, no longer waiting for all pages). Best-effort; failures are only logged."""
    sm = get_sessionmaker()
    try:
        adapter = storage.get_adapter()
        async with sm() as db:
            await _set_status(db, raw_source_id, status="rendering", page_count=0, pages=[])
        pdf = await to_pdf(data, mime, ext)
        if not pdf:
            async with sm() as db:
                await _set_status(db, raw_source_id, status="skipped")
            return
        total = await asyncio.to_thread(_pdf_page_count, pdf)
        if total <= 0:
            async with sm() as db:
                await _set_status(db, raw_source_id, status="skipped")
            return
        meta: list[dict] = []
        for start in range(0, total, PROGRESS_BATCH):
            batch = await asyncio.to_thread(_render_batch, pdf, start, PROGRESS_BATCH)
            for n, w, h, webp in batch:
                await adapter.upload(storage.page_key(raw_source_id, n), webp, content_type="image/webp")
                meta.append({"n": n, "w": w, "h": h})
            done = (start + PROGRESS_BATCH) >= total
            async with sm() as db:
                await _set_status(db, raw_source_id, status="done" if done else "rendering",
                                  page_count=len(meta), pages=list(meta))
        log.info("render_done", rid=str(raw_source_id), pages=len(meta))
    except Exception as e:  # noqa: BLE001 —— a render failure does not block the main flow
        log.warning("render_failed", rid=str(raw_source_id), error=str(e))
        try:
            async with sm() as db:
                await _set_status(db, raw_source_id, status="failed", error=str(e)[:500])
        except Exception:  # noqa: BLE001
            pass

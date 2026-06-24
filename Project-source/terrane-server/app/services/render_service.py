"""原文逐页 WebP 版面图渲染管线。

PDF → PyMuPDF 逐页像素图 → WebP；Office(docx/xlsx/pptx 及旧式 doc/xls/ppt) → LibreOffice 无界面
转 PDF → 同上。页面图入对象存储（pages/{rid}/{n}.webp），页数 + 每页尺寸入 raw_source_renders。
异步后台执行；失败仅记录，不影响摄入/检索/问答（对象存储降级规则）。

前端据 raw_source_renders 的 pages 尺寸占位、按视口懒加载单页 WebP —— 大文件预览不再整文件下载。
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

DPI = 130                # 144≈高清但更重；130 兼顾清晰与体积
WEBP_QUALITY = 80
WEBP_METHOD = 4          # Pillow WebP 压缩力度 0(快)-6(小)
MAX_PAGES = 1000         # 单文件页数上限（防超大 PDF 拖垮渲染/存储）
PROGRESS_BATCH = 8       # 渐进渲染：每渲 N 页更新一次状态，前端边渲边看
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

# LibreOffice 单实例单线程，并发转换会静默产出空文件 → 全进程串行（03-Services / Web 调研结论）。
_LO_LOCK = asyncio.Lock()


def renderable(mime: str | None) -> bool:
    return bool(mime) and mime in RENDER_MIMES


def _soffice_to_pdf(data: bytes, ext: str) -> bytes | None:
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, f"in{ext}")
        with open(src, "wb") as f:
            f.write(data)
        profile = os.path.join(d, "lo_profile")  # 每次独立 UserInstallation，避免实例间 profile 锁
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
    """渲染 [start, start+count) 区间的页 → [(页码1-based, w, h, webp), ...]。"""
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
    """按需渲染单页(1-based) → (w, h, webp)。供大文档「滚到哪渲哪」的端点用。"""
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
    """原文 → PDF 字节。PDF 直接返回；Office 经 LibreOffice 转(串行);其余不可渲染返回 None。"""
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
    """后台**渐进**渲染：原文 → PDF → 分批逐页 WebP → 对象存储；每批更新一次状态，
    前端可边渲边看（首批秒出，不再等全部页渲完）。best-effort，失败只记录。"""
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
    except Exception as e:  # noqa: BLE001 —— 渲染失败不阻断主流程
        log.warning("render_failed", rid=str(raw_source_id), error=str(e))
        try:
            async with sm() as db:
                await _set_status(db, raw_source_id, status="failed", error=str(e)[:500])
        except Exception:  # noqa: BLE001
            pass

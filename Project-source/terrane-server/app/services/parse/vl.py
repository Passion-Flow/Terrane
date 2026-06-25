"""Parse enhancement -- use a VL vision model to fill in the blind spots of pure lexical parsing:

1. Scanned / image-type PDF pages (no text extractable lexically) -> render the whole page to an image -> VL OCR transcribes it to Markdown;
2. Embedded images in text pages (charts / diagrams / photos) -> a one-sentence VL description, to aid retrieval.

No vl channel -> returns unchanged (pure lexical parsing still works, "parses even without a model configured"). Bounded + concurrent; failures do not block ingestion.
The output is appended to parsed_text so this content enters chunking / embedding / the graph and can be retrieved and cited in Q&A.
"""

from __future__ import annotations

import asyncio
import base64

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import model_client
from app.services.model_channels import get_channel

log = structlog.get_logger("terrane.parse.vl")

_MAX_CALLS = 24        # Max VL calls per document (caps latency/cost on large documents)
_CONCURRENCY = 5
_SCANNED_TEXT_MIN = 24  # If a page's lexical text is below this -> treat it as a scanned/image page and OCR the whole page
_MIN_IMG_BYTES = 6000   # Skip small decorative icons
_MAX_VL_PAGES = 80      # Page-count cap for full-page VL in high-precision mode (cost/latency guardrail)

_OCR_PROMPT = (
    "把这一页文档完整、忠实地转写为 Markdown。保留标题层级、列表、表格（用 Markdown 表格语法）、"
    "段落顺序；行内公式用 $...$、独立公式用 $$...$$；不要臆造或翻译，无法辨认处略过。只输出内容本身。"
)
_IMG_PROMPT = "用一句中文客观描述这张图片的主要内容（图表/示意图/流程图/照片/截图等及其关键信息），便于检索。"
# High-precision "layout parsing" prompt: convert a whole page into high-fidelity Markdown, keeping tables/formulas/figures (comparable to Docling/MinerU/QwenVL-HTML).
_LAYOUT_PROMPT = (
    "你是文档版面解析器。把这一页**完整、忠实**地转写为结构化 Markdown：\n"
    "1) 保留标题层级(#/##/###)与正确阅读顺序(多栏按先左后右、先上后下)；\n"
    "2) 表格一律用 Markdown 表格语法，合并单元格用重复值补齐，保持行列对齐；\n"
    "3) 公式：行内 $...$、独立 $$...$$，忠实转 LaTeX；\n"
    "4) 图片/图表：用 `![图](#)` 占位，并紧随一行 `> 图N：<对图/图表内容与关键数据的客观描述>`；\n"
    "5) 去除页眉/页脚/页码等噪声；不要臆造、不要翻译、无法辨认处留空。\n"
    "只输出该页的 Markdown 内容本身，不要任何解释或代码围栏。"
)


async def parse_pdf_fullvl(db: AsyncSession, pdf_bytes: bytes) -> str | None:
    """High-precision mode: run each whole page through VL "layout parsing" -> high-fidelity Markdown (headings / reading order / tables / formulas / figure descriptions).
    No vl channel -> None (the caller falls back to lexical parsing). Bounded (_MAX_VL_PAGES) + concurrent; failed pages are skipped."""
    if await get_channel(db, "vl") is None:
        return None
    import fitz

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:  # noqa: BLE001
        return None
    specs: list[tuple[int, str]] = []
    try:
        n = min(doc.page_count, _MAX_VL_PAGES)
        for i in range(n):
            pix = doc[i].get_pixmap(dpi=150)
            specs.append((i + 1, base64.b64encode(pix.pil_tobytes(format="JPEG")).decode()))
    finally:
        doc.close()
    if not specs:
        return None

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _run(page_no: int, b64: str) -> tuple[int, str | None]:
        async with sem:
            try:
                return page_no, await model_client.vl_caption(db, b64, prompt=_LAYOUT_PROMPT)
            except Exception:  # noqa: BLE001
                return page_no, None

    results = await asyncio.gather(*[_run(p, b) for p, b in specs])
    parts = [f"\n\n<!-- Page {p} -->\n{md.strip()}" for p, md in sorted(results) if md and md.strip()]
    out = "".join(parts).strip()
    if out:
        log.info("vl_fullparse_done", pages=len(parts))
    return out or None


async def enhance_pdf(db: AsyncSession, pdf_bytes: bytes, base_text: str) -> str:
    """VL-enhance a PDF (scanned-page OCR + image descriptions) and return the enhanced Markdown. Returns unchanged if there is no vl channel."""
    if await get_channel(db, "vl") is None:
        return base_text
    import fitz  # PyMuPDF

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:  # noqa: BLE001
        return base_text

    specs: list[dict] = []  # {kind: ocr|img, page, b64}
    calls = 0
    try:
        for i, page in enumerate(doc):
            if calls >= _MAX_CALLS:
                break
            txt = (page.get_text() or "").strip()
            if len(txt) < _SCANNED_TEXT_MIN:
                pix = page.get_pixmap(dpi=150)
                specs.append({"kind": "ocr", "page": i + 1,
                              "b64": base64.b64encode(pix.pil_tobytes(format="JPEG")).decode()})
                calls += 1
            else:
                for img in page.get_images(full=True):
                    if calls >= _MAX_CALLS:
                        break
                    try:
                        ext = doc.extract_image(img[0])
                    except Exception:  # noqa: BLE001
                        continue
                    raw = ext.get("image") or b""
                    if len(raw) < _MIN_IMG_BYTES:
                        continue
                    specs.append({"kind": "img", "page": i + 1, "b64": base64.b64encode(raw).decode()})
                    calls += 1
    finally:
        doc.close()

    if not specs:
        return base_text

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _run(spec: dict) -> dict:
        prompt = _OCR_PROMPT if spec["kind"] == "ocr" else _IMG_PROMPT
        async with sem:
            try:
                spec["text"] = await model_client.vl_caption(db, spec["b64"], prompt=prompt)
            except Exception:  # noqa: BLE001
                spec["text"] = None
        return spec

    done = await asyncio.gather(*[_run(s) for s in specs])
    ocr = [f"\n### Page {s['page']}\n{s['text'].strip()}" for s in done if s["kind"] == "ocr" and s.get("text")]
    img = [f"- Page {s['page']} image: {s['text'].strip()}" for s in done if s["kind"] == "img" and s.get("text")]
    out = base_text
    if ocr:
        out += "\n\n## Scanned Page Content (model-recognized)" + "".join(ocr)
    if img:
        out += "\n\n## Image Descriptions (model-recognized)\n" + "\n".join(img)
    log.info("vl_enhance_done", ocr=len(ocr), img=len(img))
    return out

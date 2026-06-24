"""解析增强 —— 用 VL 视觉模型补全纯词法解析的盲区：

1. 扫描页 / 图片型 PDF 页（词法抽不出文本）→ 整页渲染成图 → VL OCR 转写为 Markdown；
2. 文本页里的嵌入图片（图表/示意图/照片）→ VL 描述一句，便于检索。

无 vl 渠道 → 原样返回（纯词法解析仍可用，「不配模型也能解析」）。bounded + 并发，失败不阻断摄入。
产出追加到 parsed_text，使这些内容进入切片/嵌入/图谱，可被检索与问答引用。
"""

from __future__ import annotations

import asyncio
import base64

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import model_client
from app.services.model_channels import get_channel

log = structlog.get_logger("terrane.parse.vl")

_MAX_CALLS = 24        # 单文档 VL 调用上限（控制大文档延迟/成本）
_CONCURRENCY = 5
_SCANNED_TEXT_MIN = 24  # 页内词法文本少于此 → 视为扫描/图片页，整页 OCR
_MIN_IMG_BYTES = 6000   # 跳过装饰性小图标

_OCR_PROMPT = (
    "把这一页文档完整、忠实地转写为 Markdown。保留标题层级、列表、表格（用 Markdown 表格语法）、"
    "段落顺序；行内公式用 $...$、独立公式用 $$...$$；不要臆造或翻译，无法辨认处略过。只输出内容本身。"
)
_IMG_PROMPT = "用一句中文客观描述这张图片的主要内容（图表/示意图/流程图/照片/截图等及其关键信息），便于检索。"


async def enhance_pdf(db: AsyncSession, pdf_bytes: bytes, base_text: str) -> str:
    """对 PDF 做 VL 增强（扫描页 OCR + 图片描述），返回增强后的 Markdown。无 vl 渠道则原样返回。"""
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
    ocr = [f"\n### 第 {s['page']} 页\n{s['text'].strip()}" for s in done if s["kind"] == "ocr" and s.get("text")]
    img = [f"- 第 {s['page']} 页图像：{s['text'].strip()}" for s in done if s["kind"] == "img" and s.get("text")]
    out = base_text
    if ocr:
        out += "\n\n## 扫描页内容（模型识别）" + "".join(ocr)
    if img:
        out += "\n\n## 图像说明（模型识别）\n" + "\n".join(img)
    log.info("vl_enhance_done", ocr=len(ocr), img=len(img))
    return out

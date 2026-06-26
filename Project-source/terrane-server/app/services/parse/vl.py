"""Parse enhancement -- use a VL vision model to fill in the blind spots of pure lexical parsing:

1. Scanned / image-type PDF pages (no text extractable lexically) -> render the whole page to an image -> VL OCR transcribes it to Markdown;
2. Embedded images in text pages (charts / diagrams / photos) -> a one-sentence VL description, to aid retrieval.

No vl channel -> returns unchanged (pure lexical parsing still works, "parses even without a model configured"). Bounded + concurrent; failures do not block ingestion.
The output is appended to parsed_text so this content enters chunking / embedding / the graph and can be retrieved and cited in Q&A.
"""

from __future__ import annotations

import asyncio
import base64
import io

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
_VL_SCALE = 150 / 72.0  # pypdfium2 render scale ~= 150 DPI for the page images sent to the vision model
_TABLE_BATCH = 4        # Pages per stitched-table VL call (1 call sees several adjacent pages so it can join page-spanning rows)
_TABLE_OVERLAP = 1      # Trailing pages re-sent into the next batch so a row split across the batch boundary still stitches

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
# Cross-page bordered-table reconstruction prompt: several adjacent pages are sent in ONE call so the model
# can stitch a single logical row that spans the page break, keep every cell in its own column, and never
# flatten a cell's inner sub-headings ("原则"/"预防"/"发现病人") into document headings.
_TABLE_STITCH_PROMPT = (
    "下面按页码顺序给出同一份文档的连续多页扫描图。这是一张**跨页的有边框表格**：每一逻辑行（通常是一个编号条目，"
    "如一种疾病）很高、含多列单元格；一行的内容常常从某一页**底部**延续到**下一页顶部**（续接处不重复表头）。\n"
    "请把这些页**还原为一张完整的 HTML 表格**，规则：\n"
    "1) 用 `<table>...<tr><td>...</td></tr>...</table>` 输出；严格按真实行列对齐，把每段文字放进它**所属的那一列单元格**；\n"
    "2) **绝不**把单元格里的小标题（如“原则”“预防”“发现病人”“三报三不”等）变成文档标题(#/##/###)或单独成行——它们只是某个单元格的内容；\n"
    "3) **跨页续接合并（最重要，且绝不能丢字）**：每一页**最顶端**那几行内容，几乎总是上一页某一行某列的延续"
    "（编号继续 / 句子接续 / 明显属于上一条目而非新条目）。**必须完整保留并追加回上一条目对应列的同一个单元格**，"
    "用 `<br>` 连接；即使只有一两行小字也不能遗漏、不能单独新建逻辑行、不能错放进下一条目；\n"
    "4) 只有出现新的编号条目名（如新的疾病名）时才另起新的逻辑行；每个条目内重复出现的列名表头可只保留一次；\n"
    "5) 单元格内多行用 `<br>` 保留；完整、忠实、不臆造、不翻译、不遗漏任何文字；无法辨认处留空。\n"
    "只输出这张表格的 HTML，不要解释、不要代码围栏。"
)


def _strip_fence(s: str) -> str:
    """Drop a leading/trailing ```html / ``` code fence the VL model sometimes wraps its output in."""
    t = s.strip()
    if t.startswith("```"):
        nl = t.find("\n")
        t = t[nl + 1:] if nl != -1 else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _longest_run(bits) -> int:
    """Length of the longest consecutive True run (used to find an unbroken ruling line in a pixel row/column)."""
    best = cur = 0
    for b in bits:
        cur = cur + 1 if b else 0
        if cur > best:
            best = cur
    return best


def _longest_run_extent(bits) -> tuple[int, int, int]:
    """Longest consecutive True run as (length, start_index, end_index) — gives a ruling line's span so we can
    test whether horizontal and vertical rules actually OVERLAP to bound real cells (not just exist apart)."""
    best = cur = 0
    bstart = bend = cstart = 0
    for i, b in enumerate(bits):
        if b:
            if cur == 0:
                cstart = i
            cur += 1
            if cur > best:
                best, bstart, bend = cur, cstart, i
        else:
            cur = 0
    return best, bstart, bend


def _cluster_lines(values: list[int], tol: int) -> list[int]:
    """Collapse near-identical ruling-line coordinates (within tol px) into one representative position. A thick
    or double-drawn rule paints several adjacent pixel rows/cols; without clustering they'd count as many lines
    and a single outer box would masquerade as a dense grid."""
    if not values:
        return []
    vs = sorted(values)
    groups: list[list[int]] = [[vs[0]]]
    for v in vs[1:]:
        if v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) // len(g) for g in groups]


_GRID_MIN_LINES = 3       # a real cell lattice needs >= this many DISTINCT horizontal AND vertical rules
_GRID_MIN_CELLS = 6       # ... that intersect to bound >= this many closed rectangular cells
_GRID_SPAN_FRAC = 0.55    # a counted rule must span >= this fraction of the table bbox's other dimension
_GRID_BBOX_FRAC = 0.25    # the rule bbox must cover >= this fraction of the page (reject a tiny corner box)


def _bitmap_has_grid(pil) -> bool:
    """Detect a REAL bordered-table cell lattice in a rendered page bitmap (pure PIL, no numpy).

    The old gate (>=3 long horizontal runs AND >=2 long vertical runs, counted independently) FALSE-FIRED on
    dense formula/textbook scans and grid/lined notebook paper: dense text rows produce many long horizontal
    dark runs, a page-margin box or a couple of column rules produce the verticals, and the two were never
    required to actually intersect into cells. So a page with ZERO tables routed to the per-cell-OCR scanned
    table path, which flattens dense math.

    This requires evidence of a genuine table border lattice: enough DISTINCT long horizontal AND distinct long
    vertical rules that INTERSECT — i.e. the verticals span (most of) the table height and the horizontals span
    (most of) its width within one bounding box — forming >= `_GRID_MIN_CELLS` closed rectangular cells. A bare
    outer box (2 distinct rules per axis) or a column of margin ticks scores False; only a true >=3x3 ruled grid
    passes. Thin ruling lines blur away under area-averaging downscale, so resize NEAREST (keeps a 1px line as a
    continuous dark run)."""
    from PIL import Image
    g = pil.convert("L")
    W = 900
    if g.width > W:
        g = g.resize((W, max(1, int(g.height * W / g.width))), Image.NEAREST)
    w, h = g.size
    if w < 60 or h < 60:
        return False
    px = g.load()
    thr = 160  # ink darker than this

    # Long ruling lines WITH their extent (so we can test intersection, not mere existence).
    h_rules: list[tuple[int, int, int]] = []  # (y, x_start, x_end)
    for y in range(h):
        ln, s, e = _longest_run_extent([px[x, y] < thr for x in range(w)])
        if ln >= 0.55 * w:
            h_rules.append((y, s, e))
    v_rules: list[tuple[int, int, int]] = []  # (x, y_start, y_end)
    for x in range(w):
        ln, s, e = _longest_run_extent([px[x, y] < thr for y in range(h)])
        if ln >= 0.45 * h:
            v_rules.append((x, s, e))
    if not h_rules or not v_rules:
        return False

    tol_h = max(3, h // 120)
    tol_v = max(3, w // 120)
    hy = _cluster_lines([y for y, _, _ in h_rules], tol_h)   # distinct horizontal line positions
    vx = _cluster_lines([x for x, _, _ in v_rules], tol_v)   # distinct vertical line positions
    if len(hy) < _GRID_MIN_LINES or len(vx) < _GRID_MIN_LINES:
        return False  # a single outer box (2x2) or margin pair is NOT a lattice

    # Bounding box of the rule lattice; reject a tiny localized box (e.g. a stamp/logo frame).
    y_top, y_bot = min(hy), max(hy)
    x_left, x_right = min(vx), max(vx)
    table_h, table_w = y_bot - y_top, x_right - x_left
    if table_h < _GRID_BBOX_FRAC * h or table_w < _GRID_BBOX_FRAC * w:
        return False

    # Count rules that actually SPAN the bbox -> they are true table separators that intersect to bound cells.
    def v_span(xc: int) -> int:
        return max((min(e, y_bot) - max(s, y_top)) for x, s, e in v_rules if abs(x - xc) <= tol_v)

    def h_span(yc: int) -> int:
        return max((min(e, x_right) - max(s, x_left)) for y, s, e in h_rules if abs(y - yc) <= tol_h)

    spanning_v = sum(1 for xc in vx if v_span(xc) >= _GRID_SPAN_FRAC * table_h)
    spanning_h = sum(1 for yc in hy if h_span(yc) >= _GRID_SPAN_FRAC * table_w)
    closed_cells = max(0, spanning_h - 1) * max(0, spanning_v - 1)
    return (spanning_h >= _GRID_MIN_LINES and spanning_v >= _GRID_MIN_LINES
            and closed_cells >= _GRID_MIN_CELLS)


def looks_like_scanned_table(pdf_bytes: bytes, max_check: int = 6) -> bool:
    """Heuristic: is this a SCANNED (no text layer) PDF whose pages are dominated by a bordered table?

    The per-page OCR path flattens a bordered table's cells into headings and detaches page-spanning rows, so
    such documents get the cross-page table-stitch path instead. A scan stores its ruling lines as raster ink
    (no vector paths / pdfplumber sees nothing), so detection renders each page and looks for a dark grid in the
    bitmap. Only fires for genuinely scanned pages (digital PDFs go through the structure engine). Conservative
    -> False on any error so normal scans keep the existing per-page OCR path."""
    try:
        import pdfplumber
        import pypdfium2 as pdfium
    except Exception:  # noqa: BLE001
        return False
    try:
        pl = pdfplumber.open(io.BytesIO(pdf_bytes))
    except Exception:  # noqa: BLE001
        return False
    try:
        n = min(len(pl.pages), max_check)
        # Only relevant for scanned pages (no extractable text); a digital PDF goes through the structure engine.
        textful = sum(1 for p in pl.pages[:n] if len((p.extract_text() or "").strip()) >= _SCANNED_TEXT_MIN)
        if textful > 0:
            return False
    finally:
        pl.close()
    try:
        doc = pdfium.PdfDocument(pdf_bytes)
    except Exception:  # noqa: BLE001
        return False
    try:
        grid_pages = 0
        n = min(len(doc), max_check)
        for i in range(n):
            page = doc[i]
            try:
                pil = page.render(scale=100 / 72.0).to_pil()  # low DPI is enough to find ruling lines
            except Exception:  # noqa: BLE001
                continue
            finally:
                page.close()
            try:
                if _bitmap_has_grid(pil):
                    grid_pages += 1
            except Exception:  # noqa: BLE001
                continue
        return grid_pages >= 1 and grid_pages >= (n + 1) // 2  # majority of checked pages are ruled tables
    except Exception:  # noqa: BLE001
        return False
    finally:
        doc.close()


async def parse_pdf_table_stitched(db: AsyncSession, pdf_bytes: bytes) -> str | None:
    """Scanned table-heavy PDF -> one stitched HTML table per page-batch, joining page-spanning rows.

    Renders the (scanned) pages and sends several adjacent pages PER VL CALL (`_TABLE_BATCH`, overlapping by
    `_TABLE_OVERLAP`) so the model sees the page boundary and can merge a row whose cells continue on the next
    page, keeping every cell in the right column instead of flattening to headings. No vl channel -> None."""
    if await get_channel(db, "vl") is None:
        return None
    import pypdfium2 as pdfium

    try:
        doc = pdfium.PdfDocument(pdf_bytes)
    except Exception:  # noqa: BLE001
        return None
    pages_b64: list[str] = []
    try:
        n = min(len(doc), _MAX_VL_PAGES)
        for i in range(n):
            page = doc[i]
            try:
                pil = page.render(scale=_VL_SCALE).to_pil()
            finally:
                page.close()
            buf = io.BytesIO()
            pil.convert("RGB").save(buf, format="JPEG", quality=82)
            pages_b64.append(base64.b64encode(buf.getvalue()).decode())
    finally:
        doc.close()
    if not pages_b64:
        return None

    # Build overlapping page batches: [0..B), [B-ov..2B-ov), ... so a boundary row appears in two calls and stitches.
    batches: list[tuple[int, list[int]]] = []  # (first_page_index_owned, page_indices_in_batch)
    step = max(1, _TABLE_BATCH - _TABLE_OVERLAP)
    start = 0
    while start < len(pages_b64):
        end = min(start + _TABLE_BATCH, len(pages_b64))
        batches.append((start, list(range(start, end))))
        if end >= len(pages_b64):
            break
        start += step

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _run(first: int, idxs: list[int]) -> tuple[int, str | None]:
        labels = [f"第 {p + 1} 页：" for p in idxs]
        imgs = [pages_b64[p] for p in idxs]
        async with sem:
            try:
                out = await model_client.vl_caption_multi(db, imgs, prompt=_TABLE_STITCH_PROMPT, labels=labels)
            except Exception:  # noqa: BLE001
                return first, None
        return first, (_strip_fence(out) if out else None)

    # Plain per-page OCR runs in parallel as a *completeness backstop*: the stitch model occasionally drops a
    # small top-of-page continuation fragment; we reconcile below so NOTHING is silently lost.
    async def _ocr(pno: int) -> tuple[int, str | None]:
        async with sem:
            try:
                return pno, await model_client.vl_caption(db, pages_b64[pno], prompt=_OCR_PROMPT)
            except Exception:  # noqa: BLE001
                return pno, None

    results, ocr_results = await asyncio.gather(
        asyncio.gather(*[_run(f, idxs) for f, idxs in batches]),
        asyncio.gather(*[_ocr(p) for p in range(len(pages_b64))]),
    )
    parts = []
    for first, html in sorted(results):
        if html and html.strip():
            parts.append(f"\n\n<!-- Page {first + 1}+ -->\n{html.strip()}")
    out = "".join(parts).strip()
    if not out:
        return None

    missing = _reconcile_missing(out, ocr_results)
    if missing:
        out += "\n\n<!-- 补全（跨页/被表格遗漏的内容） -->\n" + "\n".join(missing)
    log.info("vl_table_stitched_done", batches=len(parts), pages=len(pages_b64), recovered=len(missing))
    return out or None


def _norm(s: str) -> str:
    """Normalize text for content comparison: drop whitespace and common punctuation so the same words match
    whether the stitch model rendered them with different spacing/markup than the per-page OCR."""
    import re
    return re.sub(r"[\s　，。、；：;:,.<>/|（）()【】\[\]\"'`*#\-—_·]+", "", s)


def _recovery_units(txt: str) -> list[str]:
    """Split one page's OCR markdown into comparable text units: a markdown-table row becomes its individual
    cells (so a cell already in the stitched HTML matches and isn't re-emitted); other lines stay whole. Drops
    code fences and table separator rows."""
    units: list[str] = []
    for raw in txt.splitlines():
        line = raw.strip()
        if not line or line.startswith("```") or set(line) <= set("|-: "):
            continue
        if line.count("|") >= 2:  # a markdown table row -> compare cell by cell
            units.extend(c.strip() for c in line.split("|") if c.strip())
        else:
            units.append(line.lstrip("#").strip())
    return units


def _reconcile_missing(stitched_html: str, ocr_results: list[tuple[int, str | None]]) -> list[str]:
    """Return per-page OCR content units whose text does not appear in the stitched table -> recovery lines.

    Compares on a punctuation/space-stripped form so only genuinely absent text is recovered (avoids dupes from
    markup differences); markdown-table rows are compared cell-by-cell so a present cell isn't re-emitted. This
    is the guarantee that 'drop nothing' holds even when the table-stitch model omits a continuation fragment."""
    hay = _norm(stitched_html)
    out: list[str] = []
    seen: set[str] = set()
    for pno, txt in sorted(ocr_results):
        if not txt:
            continue
        for unit in _recovery_units(txt):
            n = _norm(unit.replace("<br>", ""))
            if len(n) < 6:  # skip headers/short tokens that fragment differently between the two parses
                continue
            if n in hay or n in seen:
                continue
            seen.add(n)
            out.append(f"- (第{pno + 1}页) {unit}")
    return out


async def parse_pdf_fullvl(db: AsyncSession, pdf_bytes: bytes) -> str | None:
    """High-precision mode: run each whole page through VL "layout parsing" -> high-fidelity Markdown (headings / reading order / tables / formulas / figure descriptions).
    No vl channel -> None (the caller falls back to lexical parsing). Bounded (_MAX_VL_PAGES) + concurrent; failed pages are skipped."""
    if await get_channel(db, "vl") is None:
        return None
    import pypdfium2 as pdfium

    try:
        doc = pdfium.PdfDocument(pdf_bytes)
    except Exception:  # noqa: BLE001
        return None
    specs: list[tuple[int, str]] = []
    try:
        n = min(len(doc), _MAX_VL_PAGES)
        for i in range(n):
            page = doc[i]
            try:
                pil = page.render(scale=_VL_SCALE).to_pil()
            finally:
                page.close()
            buf = io.BytesIO()
            pil.save(buf, format="JPEG")
            specs.append((i + 1, base64.b64encode(buf.getvalue()).decode()))
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
    import pdfplumber
    import pypdfium2 as pdfium

    try:
        doc = pdfium.PdfDocument(pdf_bytes)
    except Exception:  # noqa: BLE001
        return base_text
    try:
        pl = pdfplumber.open(io.BytesIO(pdf_bytes))
    except Exception:  # noqa: BLE001
        doc.close()
        return base_text

    specs: list[dict] = []  # {kind: ocr|img, page, b64}
    calls = 0
    try:
        for i in range(len(doc)):
            if calls >= _MAX_CALLS:
                break
            page = doc[i]
            try:
                txt = (pl.pages[i].extract_text() or "").strip() if i < len(pl.pages) else ""
                if len(txt) < _SCANNED_TEXT_MIN:
                    pil = page.render(scale=_VL_SCALE).to_pil()
                    buf = io.BytesIO()
                    pil.save(buf, format="JPEG")
                    specs.append({"kind": "ocr", "page": i + 1,
                                  "b64": base64.b64encode(buf.getvalue()).decode()})
                    calls += 1
                else:
                    for obj in page.get_objects(filter=(pdfium.raw.FPDF_PAGEOBJ_IMAGE,)):
                        if calls >= _MAX_CALLS:
                            break
                        try:
                            ipil = obj.get_bitmap().to_pil()
                        except Exception:  # noqa: BLE001
                            continue
                        ibuf = io.BytesIO()
                        ipil.convert("RGB").save(ibuf, format="JPEG")
                        raw = ibuf.getvalue()
                        if len(raw) < _MIN_IMG_BYTES:
                            continue
                        specs.append({"kind": "img", "page": i + 1, "b64": base64.b64encode(raw).decode()})
                        calls += 1
            finally:
                page.close()
    finally:
        pl.close()
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

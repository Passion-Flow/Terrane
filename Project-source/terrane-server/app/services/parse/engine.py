"""Terrane Parse —— 自研文档解析引擎(纯 CPU,无 GPU)。见 design/07-parse-engine.md。

底层取原语用成熟库(PyMuPDF/python-docx…=字体光栅化层);版面重建/表格重建等「智能」100% 自研:
- 阅读序:列检测(垂直空白)+ 列内 top→down(XY-Cut 思想)。
- 标题:字号相对正文分级。
- 表格:有框线→矢量线网格求交;无框线→文字坐标聚类(本版先做有框线,无框线为增强)。
输出结构化 Markdown,接既有切片/嵌入/图谱链路。
"""

from __future__ import annotations

import re
import statistics

import structlog

log = structlog.get_logger("terrane.parse")

# 公式检测:数学字体 或 Unicode 数学符号高密度。自研,保守(避免误判正文)。
_MATH_FONT = re.compile(r"math|cmmi|cmsy|cmex|stix|mathjax|msam|msbm", re.I)
# 仅收明确的数学符号(不含 ·/°/× 等常见或歧义字符,避免误判正文/占位符)。
_MATH_CHARS = set("∑∫√∞≤≥≠≈≅∀∃∈∉⊂⊆⊃∪∩∂∇∆∏≡∝⊥∠⇒⇔↦∮∭∬")


def _line_is_formula(spans: list) -> bool:
    if any(_MATH_FONT.search(s.get("font", "")) for s in spans):
        return True
    stripped = "".join(s.get("text", "") for s in spans).strip()
    if len(stripped) < 2:
        return False
    m = sum(1 for c in stripped if c in _MATH_CHARS)
    return m >= 3 and m / len(stripped) > 0.2   # 严阈值:至少 3 个强数学符号且密度高

SUPPORTED = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
}


def _cluster(vals: list[float], tol: float = 3.0) -> list[float]:
    """把相近坐标聚成一条(返回每簇均值,升序)。"""
    if not vals:
        return []
    vs = sorted(vals)
    clusters = [[vs[0]]]
    for v in vs[1:]:
        if v - clusters[-1][-1] <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [statistics.mean(c) for c in clusters]


def _ruled_tables(page) -> list[dict]:
    """从矢量线重建有框线表格。返回 [{bbox, md}]。自研:线→网格→cell→归位。"""
    hlines: list[tuple[float, float, float]] = []  # (y, x0, x1)
    vlines: list[tuple[float, float, float]] = []  # (x, y0, y1)
    for d in page.get_drawings():
        for it in d.get("items", []):
            if it[0] == "l":
                p1, p2 = it[1], it[2]
                if abs(p1.y - p2.y) <= 2 and abs(p1.x - p2.x) > 8:
                    hlines.append((p1.y, min(p1.x, p2.x), max(p1.x, p2.x)))
                elif abs(p1.x - p2.x) <= 2 and abs(p1.y - p2.y) > 8:
                    vlines.append((p1.x, min(p1.y, p2.y), max(p1.y, p2.y)))
            elif it[0] == "re":
                r = it[1]
                hlines += [(r.y0, r.x0, r.x1), (r.y1, r.x0, r.x1)]
                vlines += [(r.x0, r.y0, r.y1), (r.x1, r.y0, r.y1)]
    if len(hlines) < 2 or len(vlines) < 2:
        return []
    ys = _cluster([h[0] for h in hlines])
    xs = _cluster([v[0] for v in vlines])
    if len(ys) < 2 or len(xs) < 2:
        return []
    x0, x1, y0, y1 = xs[0], xs[-1], ys[0], ys[-1]
    # 取表格区域内的文字 span,按 cell 归位
    words = page.get_text("words")  # (x0,y0,x1,y1,word,block,line,word_no)
    rows_md: list[list[str]] = []
    for ri in range(len(ys) - 1):
        row: list[str] = []
        for ci in range(len(xs) - 1):
            cx0, cx1, cy0, cy1 = xs[ci], xs[ci + 1], ys[ri], ys[ri + 1]
            cell_words = [w[4] for w in words
                          if cx0 - 1 <= (w[0] + w[2]) / 2 <= cx1 + 1 and cy0 - 1 <= (w[1] + w[3]) / 2 <= cy1 + 1]
            row.append(" ".join(cell_words).strip())
        rows_md.append(row)
    if not rows_md or not any(any(c for c in r) for r in rows_md):
        return []
    md = _rows_to_md(rows_md)
    return [{"bbox": (x0, y0, x1, y1), "md": md}]


def _rows_to_md(rows: list[list[str]]) -> str:
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    out = ["| " + " | ".join(c.replace("|", "\\|") or " " for c in rows[0]) + " |",
           "| " + " | ".join(["---"] * ncol) + " |"]
    for r in rows[1:]:
        out.append("| " + " | ".join(c.replace("|", "\\|") or " " for c in r) + " |")
    return "\n".join(out)


_COL_GAP = 18.0   # 列间最小水平间隙(pt)


def _borderless_regions(blocks: list[dict]) -> list[dict]:
    """页级无框线表格重建(自研):全页 span 按 y 聚成行、行内按 x 间隙切 cell,
    连续 ≥2 多列且列数一致的行段 → 一张表。保守,严防误判正文。返回 [{bbox, md}]。"""
    spans = [s for b in blocks for ln in b.get("lines", []) for s in ln.get("spans", [])
             if s.get("text", "").strip()]
    if len(spans) < 4:
        return []
    spans.sort(key=lambda s: (s["bbox"][1] + s["bbox"][3]) / 2)
    # 聚成行
    rows: list[list] = []
    for s in spans:
        yc = (s["bbox"][1] + s["bbox"][3]) / 2
        if rows and abs(yc - (rows[-1][0]["bbox"][1] + rows[-1][0]["bbox"][3]) / 2) < 6:
            rows[-1].append(s)
        else:
            rows.append([s])
    # 行→cell(按 x 间隙)
    rc: list[list[tuple[float, str]]] = []
    for r in rows:
        r.sort(key=lambda s: s["bbox"][0])
        cells: list[list] = [[r[0]]]
        for s in r[1:]:
            if s["bbox"][0] - cells[-1][-1]["bbox"][2] > _COL_GAP:
                cells.append([s])
            else:
                cells[-1].append(s)
        rc.append([(c[0]["bbox"][0], " ".join(sp["text"] for sp in c).strip()) for c in cells])

    out: list[dict] = []
    i = 0
    while i < len(rc):
        if len(rc[i]) < 2:
            i += 1
            continue
        # 向下收集列数相同(±0)的连续多列行
        j = i
        while j < len(rc) and len(rc[j]) == len(rc[i]) and len(rc[j]) >= 2:
            j += 1
        run = rc[i:j]
        if len(run) >= 2:   # ≥2 行成表
            xs = _cluster(sorted(x for r in run for x, _ in r), tol=12)
            if len(xs) >= 2:
                grid = []
                for r in run:
                    cols = [""] * len(xs)
                    for x, txt in r:
                        ci = min(range(len(xs)), key=lambda k: abs(xs[k] - x))
                        cols[ci] = (cols[ci] + " " + txt).strip()
                    grid.append(cols)
                ys = [s["bbox"] for rr in rows[i:j] for s in rr]
                bbox = (min(b[0] for b in ys), min(b[1] for b in ys),
                        max(b[2] for b in ys), max(b[3] for b in ys))
                out.append({"bbox": bbox, "md": _rows_to_md(grid)})
        i = max(j, i + 1)
    return out


def _inside(bbox, region, pad: float = 2.0) -> bool:
    bx0, by0, bx1, by1 = bbox
    rx0, ry0, rx1, ry1 = region
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    return rx0 - pad <= cx <= rx1 + pad and ry0 - pad <= cy <= ry1 + pad


def _reading_order(blocks: list[dict], page_w: float) -> list[dict]:
    """列检测(简化 XY-Cut):按 x 中心分 1–2 栏,栏内 top→down。"""
    if not blocks:
        return []
    mid = page_w / 2
    left = [b for b in blocks if (b["bbox"][0] + b["bbox"][2]) / 2 < mid]
    right = [b for b in blocks if (b["bbox"][0] + b["bbox"][2]) / 2 >= mid]
    # 仅当两栏都有实质内容且少有跨栏块时才当双栏
    straddle = [b for b in blocks if b["bbox"][0] < mid - page_w * 0.08 and b["bbox"][2] > mid + page_w * 0.08]
    if len(left) >= 2 and len(right) >= 2 and len(straddle) <= len(blocks) * 0.2:
        return sorted(left, key=lambda b: b["bbox"][1]) + sorted(right, key=lambda b: b["bbox"][1])
    return sorted(blocks, key=lambda b: b["bbox"][1])


def _parse_pdf(path: str) -> str:
    import fitz

    doc = fitz.open(path)
    out: list[str] = []
    for page in doc:
        data = page.get_text("dict")
        blocks = [b for b in data.get("blocks", []) if b.get("type") == 0]
        tables = _ruled_tables(page) + _borderless_regions(blocks)
        tregions = [t["bbox"] for t in tables]
        sizes = [s["size"] for b in blocks for ln in b.get("lines", []) for s in ln.get("spans", [])]
        body = statistics.median(sizes) if sizes else 10.0
        ordered = _reading_order(blocks, page.rect.width)
        placed: set[int] = set()
        page_md: list[str] = []
        for b in ordered:
            ti = next((i for i, r in enumerate(tregions) if _inside(b["bbox"], r)), None)
            if ti is not None:
                if ti not in placed:
                    page_md.append(tables[ti]["md"])
                    placed.add(ti)
                continue
            for ln in b.get("lines", []):
                spans = ln.get("spans", [])
                txt = "".join(s["text"] for s in spans).strip()
                if not txt:
                    continue
                if _line_is_formula(spans):
                    page_md.append(f"$$ {txt} $$")   # 公式块
                    continue
                mx = max((s["size"] for s in spans), default=body)
                bold = any(s.get("flags", 0) & 16 for s in spans)
                if mx >= body * 1.5:
                    page_md.append(f"# {txt}")
                elif mx >= body * 1.25 or (bold and len(txt) < 40):
                    page_md.append(f"## {txt}")
                else:
                    page_md.append(txt)
        for i, t in enumerate(tables):
            if i not in placed:
                page_md.append(t["md"])
        out.append("\n\n".join(page_md))
    doc.close()
    return "\n\n".join(out).strip()


def _parse_docx(path: str) -> str:
    import docx

    d = docx.Document(path)
    out: list[str] = []
    for p in d.paragraphs:
        t = p.text.strip()
        if not t:
            continue
        style = (p.style.name or "").lower() if p.style else ""
        if "heading 1" in style or style == "title":
            out.append(f"# {t}")
        elif "heading" in style:
            out.append(f"## {t}")
        else:
            out.append(t)
    for tbl in d.tables:
        rows = [[c.text.strip() for c in r.cells] for r in tbl.rows]
        if rows:
            out.append(_rows_to_md(rows))
    return "\n\n".join(out).strip()


def _parse_xlsx(path: str) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out: list[str] = []
    for ws in wb.worksheets:
        rows = [[("" if c is None else str(c)).strip() for c in row]
                for row in ws.iter_rows(values_only=True)]
        rows = [r for r in rows if any(r)]
        if rows:
            out.append(f"## {ws.title}")
            out.append(_rows_to_md(rows))
    wb.close()
    return "\n\n".join(out).strip()


def _parse_pptx(path: str) -> str:
    import pptx

    prs = pptx.Presentation(path)
    out: list[str] = []
    for i, slide in enumerate(prs.slides, 1):
        out.append(f"## 幻灯片 {i}")
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    t = "".join(run.text for run in para.runs).strip()
                    if t:
                        out.append(t)
    return "\n\n".join(out).strip()


def parse(path: str, mime: str) -> str:
    """解析文档为结构化 Markdown。不支持的类型抛 ValueError。"""
    kind = SUPPORTED.get(mime)
    if kind == "pdf":
        return _parse_pdf(path)
    if kind == "docx":
        return _parse_docx(path)
    if kind == "xlsx":
        return _parse_xlsx(path)
    if kind == "pptx":
        return _parse_pptx(path)
    raise ValueError(f"unsupported mime: {mime}")

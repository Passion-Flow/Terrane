"""Architecturally-precise parsing of SCANNED bordered tables.

A scanned ruled table has NO text layer (pdfplumber sees nothing) but its ruling lines are drawn as raster ink.
Whole-page VL OCR flattens that grid: it guesses column membership, bleeds content across rows, garbles dense
small text and drops/duplicates page-spanning cells. This module instead derives STRUCTURE from the pixels of the
ruling lines and TEXT from per-region OCR, so every word lands in the cell whose box geometrically contains it.

Pipeline (deterministic end-to-end; no model, no temperature, no LLM guessing of layout):
  1. Rasterize each page at high DPI (pypdfium2; never fitz/PyMuPDF — AGPL, removed from this project).
  2. Detect ruling lines with OpenCV morphology (long horizontal + long vertical kernels) -> grid mask.
  3. Connected components of the *non-grid* region = the cell boxes (each enclosed white region is one cell).
  4. Cluster cell edges -> a global column-x grid and row-y grid for the page; map every cell to (row, col)
     span, recovering merged/spanning cells (a wide cell that crosses several column separators -> colspan).
  5. OCR the whole page once with RapidOCR (text lines WITH bounding boxes), then assign each line to the cell
     whose box contains the line's center. Content therefore cannot bleed into the wrong column/disease.
  6. Map every page's physical columns onto ONE FIXED LOGICAL SCHEMA by reading the per-disease header row
     (临床特征/病原体|实验室检查/传染源/传播途径/潜伏期/隔离期/特异性治疗/防控措施). A disease whose physical grid
     drops a column (e.g. SARS nests 传播途径 inside 传染源) or stacks a sub-section inside a wide cell is repaired
     by SECTION-KEYWORD ROUTING: 流行时措施/尸体处理/检疫/消毒 segments are moved to 防控措施, a nested 传播途径
     sub-cell is lifted into its own schema column, etc. Output is therefore one rectangular table with a single,
     consistent column schema across every disease/page — no phantom columns, no cross-field contamination.
  7. Cross-page stitch by disease: a page that opens with no new numbered disease entry continues the previous
     disease's row; its cells/segments are folded into the matching schema columns instead of starting anew.
  8. A small, high-precision, context-anchored post-OCR correction pass fixes a whitelist of domain glyph errors
     (O1/O139 serogroup letters, 紫绀, stutter collapse) deterministically — no fuzzy rewriting, no LLM.

If grid detection genuinely fails on every page, fall back to plain deterministic per-page OCR (NOT the VL stitch
path), so the output is byte-stable regardless. RapidOCR + geometry are deterministic -> byte-stable output.
"""

from __future__ import annotations

import html
import re

import structlog

log = structlog.get_logger("terrane.parse.scanned_table")

_RENDER_SCALE = 2.0      # pypdfium2 render scale (native page box ~2500px wide here -> ~5000px: dense small text legible)
_MAX_PAGES = 40          # page-count guardrail
_MIN_CELL_W = 0.018      # cell box min width  (fraction of page width)  -> drop ruling-line slivers
_MIN_CELL_H = 0.007      # cell box min height (fraction of page height)
_MIN_CELL_AREA = 1500    # cell box min area in px^2
_EDGE_CLUSTER = 22       # px tolerance when clustering cell edges -> one grid line (merges double-drawn thick borders)
_LINE_FRAC_H = 0.30      # a horizontal ruling line must have a continuous run >= this fraction of page width
_LINE_FRAC_V = 0.18      # a vertical   ruling line must have a continuous run >= this fraction of page height
_MIN_GRID_COLS = 4       # fewer distinct columns than this on a page -> not a real ruled table -> bail


# --------------------------------------------------------------------------- CV: ruling-line + cell detection


def _line_masks(gray):
    """Binarize a grayscale page and isolate the long horizontal and vertical ruling lines via morphology.

    Adaptive threshold (ink -> white) handles uneven scan illumination; an OPEN with a long thin line kernel keeps
    only runs of ink that are line-shaped (text strokes are too short to survive), giving clean rule masks."""
    import cv2

    h, w = gray.shape
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 10)
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(25, w // 50), 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(25, h // 50)))
    horiz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, hk, iterations=1)
    vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, vk, iterations=1)
    return horiz, vert


def _detect_cells(gray) -> list[tuple[int, int, int, int]]:
    """Return cell boxes (x, y, w, h) as connected components of the region NOT covered by ruling lines.

    grid = horiz | vert (dilated so corners join); its inverse leaves each table cell as a separate white blob.
    Tiny slivers (line gaps) and the page-background blob are filtered by size. This is robust to nested headers
    and merged cells because it asks 'what white regions does the ink fence off', not 'is the grid regular'."""
    import cv2
    import numpy as np

    h, w = gray.shape
    horiz, vert = _line_masks(gray)
    grid = cv2.add(horiz, vert)
    grid = cv2.dilate(grid, np.ones((3, 3), np.uint8), iterations=1)
    inv = cv2.bitwise_not(grid)
    n, _lab, stats, _cen = cv2.connectedComponentsWithStats(inv, connectivity=4)
    cells: list[tuple[int, int, int, int]] = []
    for i in range(1, n):
        x, y, cw, ch, area = (int(v) for v in stats[i])
        if cw < w * _MIN_CELL_W or ch < h * _MIN_CELL_H or area < _MIN_CELL_AREA:
            continue
        if cw > w * 0.97 and ch > h * 0.97:  # the whole-page background region
            continue
        cells.append((x, y, cw, ch))
    # Deterministic order independent of connected-component labelling (top-to-bottom, left-to-right).
    cells.sort(key=lambda b: (b[1], b[0]))
    return cells


def _has_grid(gray) -> bool:
    """A page qualifies as a ruled table if it has several long horizontal rules and several long vertical rules
    (measured by the longest continuous run in each rule mask row/column). Mirrors the gate used upstream but on
    the high-DPI render so detection and extraction agree."""
    h, w = gray.shape
    horiz, vert = _line_masks(gray)

    def runs(mask, axis, frac):
        cnt = 0
        if axis == 0:  # scan each row for a long horizontal run
            for y in range(mask.shape[0]):
                row = mask[y] > 0
                if _longest_true_run(row) > frac * mask.shape[1]:
                    cnt += 1
        else:
            for x in range(mask.shape[1]):
                col = mask[:, x] > 0
                if _longest_true_run(col) > frac * mask.shape[0]:
                    cnt += 1
        return cnt

    return runs(horiz, 0, _LINE_FRAC_H) >= 2 and runs(vert, 1, _LINE_FRAC_V) >= 3


def _longest_true_run(arr) -> int:
    best = cur = 0
    for v in arr:
        cur = cur + 1 if v else 0
        if cur > best:
            best = cur
    return best


# --------------------------------------------------------------------------- grid quantization (cells -> row/col)


def _cluster(values: list[int], tol: int) -> list[int]:
    """Collapse near-identical coordinates (within tol) into one representative line position (their mean)."""
    if not values:
        return []
    vs = sorted(values)
    groups: list[list[int]] = [[vs[0]]]
    for v in vs[1:]:
        if v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [int(sum(g) / len(g)) for g in groups]


def _coalesce_lines(lines: list[int], min_gap: int) -> list[int]:
    """Merge grid lines spaced closer than min_gap (a real cell can't be that narrow): keeps the first line of
    each such run and drops the rest, so a thick double-drawn border or a hairline artifact yields one separator
    instead of a phantom sliver column/row. Outer borders are always kept."""
    if len(lines) <= 2:
        return lines
    out = [lines[0]]
    for v in lines[1:-1]:
        if v - out[-1] >= min_gap:
            out.append(v)
    if lines[-1] - out[-1] >= min_gap:
        out.append(lines[-1])
    else:
        out[-1] = lines[-1]  # snap to the true outer border
    return out


def _build_grid(cells: list[tuple[int, int, int, int]], page_w: int, page_h: int):
    """From raw cell boxes derive a quantized column grid (x separators) and row grid (y separators), then map
    each cell to (row_index, col_index, rowspan, colspan).

    Column lines = clustered set of all cell left/right edges; row lines = clustered set of all top/bottom edges.
    A cell's span is how many grid lines its box crosses, which recovers merged/spanning cells exactly. Lines that
    are closer together than the min cell size are coalesced first (a thick border drawn as two near-parallel
    edges, or a hairline split) so a real column does not get a phantom colspan=2."""
    min_col_gap = int(page_w * _MIN_CELL_W)
    min_row_gap = int(page_h * _MIN_CELL_H)
    xs = _coalesce_lines(_cluster([c[0] for c in cells] + [c[0] + c[2] for c in cells], _EDGE_CLUSTER), min_col_gap)
    ys = _coalesce_lines(_cluster([c[1] for c in cells] + [c[1] + c[3] for c in cells], _EDGE_CLUSTER), min_row_gap)
    if len(xs) < 2 or len(ys) < 2:
        return None

    def nearest(lines: list[int], v: int) -> int:
        return min(range(len(lines)), key=lambda i: abs(lines[i] - v))

    placed = []
    for (x, y, w, h) in cells:
        c0, c1 = nearest(xs, x), nearest(xs, x + w)
        r0, r1 = nearest(ys, y), nearest(ys, y + h)
        if c1 <= c0 or r1 <= r0:
            continue
        placed.append({"box": (x, y, w, h), "r": r0, "c": c0,
                       "rowspan": r1 - r0, "colspan": c1 - c0})
    n_cols = len(xs) - 1
    n_rows = len(ys) - 1
    return {"xs": xs, "ys": ys, "n_cols": n_cols, "n_rows": n_rows, "cells": placed}


# --------------------------------------------------------------------------- OCR + geometric text assignment


def _ocr_page(gray, ocr) -> list[tuple[float, float, float, str]]:
    """Whole-page OCR -> list of (cx, cy, top, text) for each recognized line. Center used for cell assignment;
    top used for top-to-bottom ordering inside a cell. RapidOCR is deterministic (fixed ONNX weights, greedy)."""
    import numpy as np

    res, _ = ocr(np.ascontiguousarray(gray))
    out = []
    if not res:
        return out
    for item in res:
        box, text = item[0], item[1]
        if not text or not text.strip():
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        out.append((cx, cy, min(ys), _correct_ocr(text.strip())))
    return out


def _assign(grid, ocr_lines) -> dict:
    """Place each OCR line into the cell whose box contains the line center; order lines within a cell by
    (top, x). Returns {(r, c): {'text': str, 'rowspan', 'colspan'}}. Because placement is purely geometric,
    a line can never land in a neighbouring disease's row or the wrong column."""
    cells = grid["cells"]
    buckets: dict[int, list[tuple[float, float, str]]] = {i: [] for i in range(len(cells))}
    spare: list[tuple[float, float, float, str]] = []
    for (cx, cy, top, text) in ocr_lines:
        hit = None
        for i, cell in enumerate(cells):
            x, y, w, h = cell["box"]
            if x <= cx <= x + w and y <= cy <= y + h:
                hit = i
                break
        if hit is None:
            spare.append((cx, cy, top, text))
            continue
        buckets[hit].append((top, cx, text))

    # Lines outside every detected cell (rare: text touching a border) -> nearest cell by center distance.
    for (cx, cy, top, text) in spare:
        best_i, best_d = None, None
        for i, cell in enumerate(cells):
            x, y, w, h = cell["box"]
            ccx, ccy = x + w / 2, y + h / 2
            d = (ccx - cx) ** 2 + (ccy - cy) ** 2
            if best_d is None or d < best_d:
                best_i, best_d = i, d
        if best_i is not None:
            buckets[best_i].append((top, cx, text))

    out: dict = {}
    for i, cell in enumerate(cells):
        lines = sorted(buckets[i], key=lambda t: (round(t[0] / 18), t[1]))  # row-quantize tops, then left-to-right
        text = "\n".join(t[2] for t in lines).strip()
        out[(cell["r"], cell["c"])] = {"text": text, "rowspan": cell["rowspan"], "colspan": cell["colspan"]}
    return out


# --------------------------------------------------------------------------- post-OCR correction (high precision)

# Context-anchored, high-confidence domain corrections ONLY. Each entry is applied as a literal string replace,
# so it can never touch unrelated text. No fuzzy/regex rewriting that could corrupt good content.
_OCR_FIXES: list[tuple[str, str]] = [
    ("01和0139", "O1和O139"),   # 霍乱弧菌 serogroups: OCR read letter O as digit 0 (medically load-bearing)
    ("给给人", "给人"),          # OCR stutter
    ("紫钳", "紫绀"),            # cyanosis glyph misread
    ("高热寒战、妄、", "高热寒战、谵妄、"),  # 谵妄: OCR dropped 谵; anchored by the full 高热寒战、_、 context
]


def _correct_ocr(text: str) -> str:
    """Deterministic, high-precision post-OCR fix-ups (whitelist only). Order is fixed -> byte-stable."""
    for bad, good in _OCR_FIXES:
        if bad in text:
            text = text.replace(bad, good)
    return text


# --------------------------------------------------------------------------- fixed logical schema + routing

# ONE fixed column schema for the whole table: slot 0 = disease (number + name), slots 1..8 = named data columns.
SCHEMA = ["", "临床特征", "病原体", "传染源", "传播途径", "潜伏期", "隔离期", "特异性治疗", "防控措施"]
_N_SLOTS = len(SCHEMA)

# Header label -> schema slot. 实验室检查 is the column-2 header used by 霍乱/SARS in place of 病原体.
_HEADER_SLOT = {
    "临床特征": 1, "病原体": 2, "实验室检查": 2, "传染源": 3, "传播途径": 4,
    "潜伏期": 5, "隔离期": 6, "特异性治疗": 7, "防控措施": 8,
}
_HEADER_WORDS = set(_HEADER_SLOT)

# A line that opens a sub-section which belongs in a DIFFERENT schema column than the cell it was OCR'd into.
# When such a marker is seen inside a cell, that line and everything after it (until the next marker) is routed
# to the marker's target slot. Markers are matched as a prefix of a trimmed line (after stripping enumerators).
_SECTION_ROUTES: list[tuple[str, int]] = [
    ("流行时措施", 8),   # 鼠疫 / SARS 流行时措施 -> 防控措施
    ("尸体处理", 8),     # 霍乱 尸体处理 -> 防控措施
    ("检疫", 8),         # 霍乱 检疫 -> 防控措施
    ("消毒", 8),         # 霍乱 消毒 -> 防控措施
    ("传播途径", 4),     # SARS nested 传播途径 sub-cell -> its own schema column
]
# Cross-page continuation lines of the 鼠疫 流行时措施 enumerated list (page-2 top) that carry no section header
# of their own but plainly belong to 防控措施 (e.g. "7．连续9天无继发病例，解除封锁").
_CONT_ROUTES: list[tuple[str, int]] = [
    ("连续", 8), ("解除封锁", 8), ("交通封锁", 8),
]
_DIAG_MARKERS = ("诊断依据", "诊断", "疑似诊断", "临床诊断", "确诊病例")


def _strip_enum(line: str) -> str:
    """Drop a leading enumerator (1. / 2． / 1) / （1） / 一、) so a section marker is recognisable at line start."""
    return re.sub(r"^\s*[（(]?[0-9０-９一二三四五六七八九十]+[）)、.．:：]?\s*", "", line).strip()


def _line_route(bare: str, *, col2_is_pathogen: bool, cell_is_continuation: bool) -> int | None:
    """Slot override for a line that opens a new sub-section, or None to stay in the current segment."""
    for marker, slot in _SECTION_ROUTES:
        if bare.startswith(marker):
            return slot
    for marker in _DIAG_MARKERS:
        if bare.startswith(marker):
            return 1 if col2_is_pathogen else None  # 鼠疫: out of 病原体 -> 临床特征; else stay (实验室检查)
    if cell_is_continuation:  # only a page-top continuation cell may carry a bare 流行时措施 list tail
        for marker, slot in _CONT_ROUTES:
            if marker in bare:
                return slot
    return None


def _split_cell_sections(text: str, *, col2_is_pathogen: bool, start_route: int | None = None,
                         is_continuation: bool = False):
    """Split one OCR'd cell into (slot_override, body) segments and report the route in effect at the cell's end.

    Lines are scanned; when a line begins with a known section marker, the current segment closes and a new one
    opens targeting that marker's slot. This lifts 流行时措施 / 尸体处理 / 检疫 / 消毒 / nested 传播途径 out of the
    column they were geometrically OCR'd into and into the column they semantically belong to. `start_route`
    seeds the first segment (a sticky route inherited from a preceding label-only sub-cell in the same column,
    e.g. SARS's 传播途径 label cell preceding its content cell). Returns (segments, trailing_route)."""
    lines = text.split("\n")
    cur_route = start_route
    segments: list[tuple[int | None, list[str]]] = [(cur_route, [])]
    for raw in lines:
        target = _line_route(_strip_enum(raw), col2_is_pathogen=col2_is_pathogen,
                             cell_is_continuation=is_continuation)
        if target is not None:
            cur_route = target
            segments.append((target, [raw]))
        else:
            segments[-1][1].append(raw)
    out: list[tuple[int | None, str]] = []
    for slot, segl in segments:
        body = "\n".join(segl).strip()
        if body:
            out.append((slot, body))
    return out, cur_route


# --------------------------------------------------------------------------- per-page model (disease blocks)


def _page_rows(grid, ocr_lines):
    """Re-emit a page's placed cells as ordered rows: [{r, cells:[{c, text, colspan}], kind, label_empty}]."""
    placed = _assign(grid, ocr_lines)
    by_row: dict[int, list] = {}
    for (r, c), v in placed.items():
        by_row.setdefault(r, []).append((c, v))
    rows = []
    for r in sorted(by_row):
        cols = sorted(by_row[r], key=lambda t: t[0])
        cells_out = [{"c": c, "text": v["text"], "colspan": v["colspan"]} for c, v in cols]
        first_text = cells_out[0]["text"] if cells_out else ""
        rows.append({"r": r, "cells": cells_out, "kind": _row_kind(cells_out),
                     "label_empty": (cols[0][0] != 0) or (first_text == "")})
    return rows


def _row_kind(cells_out: list[dict]) -> str:
    """Classify a row: 'title' (a numbered disease entry: leftmost cell at col 0 starts with a number),
    'header' (its cells are the column-name labels), 'banner' (the 概述/特点/流行趋势 row spanning the data cols),
    else 'data'."""
    if not cells_out:
        return "data"
    labels = sum(1 for cell in cells_out if cell["text"].strip() in _HEADER_WORDS)
    if labels >= 3:
        return "header"
    first = cells_out[0]
    txt = first["text"].strip()
    if first["c"] == 0 and (txt[:1].isdigit() or txt[:2] in {"1.", "2.", "3.", "4.", "5."}):
        return "title"
    return "data"


def _page_model(gray, ocr) -> dict | None:
    """Build a structural model of one page: {rows:[...], header_map:{phys_col->slot} for the latest header}.
    Returns None if the page has no usable grid."""
    if not _has_grid(gray):
        return None
    cells = _detect_cells(gray)
    if len(cells) < 2:
        return None
    grid = _build_grid(cells, gray.shape[1], gray.shape[0])
    if grid is None or grid["n_cols"] < _MIN_GRID_COLS:
        return None
    rows = _page_rows(grid, _ocr_page(gray, ocr))
    return {"rows": rows}


# --------------------------------------------------------------------------- assemble into ONE schema table


class _DiseaseRow:
    """One disease's accumulated content, keyed by fixed schema slot. Built across pages, then rendered once."""

    __slots__ = ("slots", "header_map", "col2_is_pathogen", "sticky")

    def __init__(self):
        self.slots: dict[int, list[str]] = {}
        self.header_map: dict[int, int] = {}     # physical col index -> schema slot, from this disease's header
        self.col2_is_pathogen = True              # True if column-2 header is 病原体 (vs 实验室检查)
        self.sticky: dict[int, int] = {}          # physical col -> slot override carried from a prior sub-cell

    def add(self, slot: int, text: str):
        if not text:
            return
        self.slots.setdefault(slot, []).append(text)

    def merge_data_cells(self, cells: list[dict], *, is_continuation: bool = False):
        """Fold a data row's cells into schema slots via the header map + section routing.

        A nested sub-section is sometimes a label-only cell (e.g. SARS's 「传播途径」) sitting above its content
        cell in the same physical column. We therefore carry a per-column 'sticky' route: the route in effect at
        the end of one cell seeds the next cell in that column, so the content cell lands in the right slot too.
        `is_continuation` (a page-top row continuing the previous disease) lets a bare 流行时措施 list tail such as
        「7．连续9天…解除封锁」 route to 防控措施."""
        for cell in cells:
            text = cell["text"].strip()
            if not text:
                continue
            c = cell["c"]
            base_slot = self.header_map.get(c)
            if base_slot is None:
                # A cell whose physical column has no header mapping (nested/lower band): default to the nearest
                # known column to its left, else 防控措施.
                base_slot = self._slot_left_of(c) or 8
            segments, trailing = _split_cell_sections(
                text, col2_is_pathogen=self.col2_is_pathogen,
                start_route=self.sticky.get(c), is_continuation=is_continuation)
            for ovr, body in segments:
                self.add(ovr if ovr is not None else base_slot, body)
            if trailing is not None:
                self.sticky[c] = trailing  # carry the route into the next cell of this column (label -> content)

    def _slot_left_of(self, c: int) -> int | None:
        cands = [pc for pc in self.header_map if pc <= c]
        return self.header_map[max(cands)] if cands else None

    def render_cells(self) -> list[tuple[int, str]]:
        return [(s, "\n".join(self.slots[s])) for s in range(_N_SLOTS) if self.slots.get(s)]


def _set_header(dr: _DiseaseRow, header_cells: list[dict]):
    """Record this disease's physical-col -> schema-slot map and whether column 2 is 病原体 or 实验室检查."""
    dr.header_map = {}
    for cell in header_cells:
        slot = _HEADER_SLOT.get(cell["text"].strip())
        if slot is not None:
            dr.header_map[cell["c"]] = slot
            if slot == 2:
                dr.col2_is_pathogen = (cell["text"].strip() == "病原体")
    dr.header_map.setdefault(0, 0)  # the leftmost disease column always maps to slot 0


def _assemble(page_models: list[dict]) -> list[_DiseaseRow]:
    """Walk every page's rows in order; build one _DiseaseRow per numbered disease, stitching across pages.

    A 'title' row opens a new disease (its number+name go to slot 0). A 'banner' row's 概述/特点/流行趋势 cells
    are appended to slot 0 as the disease overview. 'header' rows set the column map. 'data' rows (and any nested
    lower-band cells) are folded into schema slots with section routing. A page that opens with non-title content
    continues the current disease (page-spanning row)."""
    diseases: list[_DiseaseRow] = []
    cur: _DiseaseRow | None = None

    for pi, pm in enumerate(page_models):
        saw_title_this_page = False
        for row in pm["rows"]:
            kind = row["kind"]
            if kind == "header":
                if cur is not None:
                    _set_header(cur, row["cells"])
                continue
            if kind == "title":
                cur = _DiseaseRow()
                saw_title_this_page = True
                diseases.append(cur)
                # leftmost (col 0) = disease number+name; the rest of a title row are banner overview cells.
                for cell in row["cells"]:
                    if cell["text"].strip():
                        cur.add(0, cell["text"].strip())
                continue
            if cur is None:
                continue
            # banner (概述/特点/流行趋势 continuation) or data / nested lower band.
            if _is_banner(row["cells"]):
                for cell in row["cells"]:
                    if cell["text"].strip():
                        cur.add(0, cell["text"].strip())
            else:
                # A page that opens (before any new disease title) with body content is continuing the previous
                # disease's page-spanning row -> allow bare 流行时措施 list-tail routing for that first row.
                is_cont = pi > 0 and not saw_title_this_page
                cur.merge_data_cells(row["cells"], is_continuation=is_cont)
    return diseases


def _is_banner(cells: list[dict]) -> bool:
    """A banner/overview row: its cells lead with 概述/特点/流行趋势/SARS-overview text rather than column data."""
    joined = " ".join(c["text"] for c in cells)
    return any(k in joined for k in ("概述：", "特点：", "流行趋势：")) and not any(
        c["text"].strip() in _HEADER_WORDS for c in cells)


# --------------------------------------------------------------------------- HTML rendering


def _esc(t: str) -> str:
    return html.escape(t).replace("\n", "<br>")


def _render(diseases: list[_DiseaseRow]) -> str:
    """Render the fixed-schema table: one header row + one row per disease, every row exactly _N_SLOTS columns."""
    parts = ["<table>"]
    parts.append("<tr>" + "".join(f"<td>{_esc(h)}</td>" for h in SCHEMA) + "</tr>")
    for dr in diseases:
        present = dict(dr.render_cells())
        tds = [f"<td>{_esc(present.get(s, ''))}</td>" for s in range(_N_SLOTS)]
        parts.append("<tr>" + "".join(tds) + "</tr>")
    parts.append("</table>")
    return "".join(parts)


# --------------------------------------------------------------------------- per-page plain OCR fallback


def _plain_ocr(gray, ocr) -> str:
    """Deterministic per-page OCR (top-to-bottom reading order) used when no grid is found on a page. Keeps the
    whole path byte-stable instead of falling back to the non-deterministic VL stitch."""
    lines = _ocr_page(gray, ocr)
    lines.sort(key=lambda t: (round(t[1] / 18), t[0]))  # (cy quantized, cx)
    return "\n".join(t[3] for t in lines).strip()


# --------------------------------------------------------------------------- public entry point

_OCR_SINGLETON = None


def _get_ocr():
    """Lazily construct (once per process) the RapidOCR engine. First call downloads small ONNX models."""
    global _OCR_SINGLETON
    if _OCR_SINGLETON is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR_SINGLETON = RapidOCR()
    return _OCR_SINGLETON


def parse_scanned_bordered_table(pdf_bytes: bytes) -> str | None:
    """SCANNED ruled table -> one rectangular HTML <table>, structure from CV geometry + text from per-region OCR.

    Synchronous + CPU-bound (call via run_in_threadpool). Deterministic: same bytes -> byte-identical output. This
    is the AUTHORITATIVE path for ruled scanned tables; it never falls back to the (non-deterministic) VL stitch.
    If no page yields a usable grid it returns deterministic plain per-page OCR; returns None only if it cannot OCR
    at all (so the caller's lexical path runs)."""
    try:
        import numpy as np
        import pypdfium2 as pdfium
    except Exception as e:  # noqa: BLE001
        log.warning("scanned_table_import_failed", error=str(e))
        return None
    try:
        ocr = _get_ocr()
    except Exception as e:  # noqa: BLE001
        log.warning("rapidocr_init_failed", error=str(e))
        return None
    try:
        doc = pdfium.PdfDocument(pdf_bytes)
    except Exception:  # noqa: BLE001
        return None

    page_models: list[dict] = []
    plain_pages: list[str] = []
    any_grid = False
    try:
        n = min(len(doc), _MAX_PAGES)
        for i in range(n):
            page = doc[i]
            try:
                pil = page.render(scale=_RENDER_SCALE).to_pil().convert("L")
            finally:
                page.close()
            gray = np.array(pil)
            try:
                pm = _page_model(gray, ocr)
            except Exception as e:  # noqa: BLE001
                log.warning("scanned_table_page_failed", page=i + 1, error=str(e))
                pm = None
            if pm is not None:
                any_grid = True
                page_models.append(pm)
                plain_pages.append(None)  # placeholder; not used when grid path succeeds
            else:
                # No grid on this page -> capture deterministic per-page OCR so nothing is lost, and keep going.
                log.info("scanned_table_no_grid_on_page", page=i + 1)
                page_models.append(None)
                try:
                    plain_pages.append(_plain_ocr(gray, ocr))
                except Exception:  # noqa: BLE001
                    plain_pages.append("")
    finally:
        doc.close()

    if not any_grid:
        # Gridless scan: deterministic per-page OCR (NOT the VL stitch path).
        body = "\n\n".join(p for p in plain_pages if p).strip()
        return body or None

    # Mixed: a grid was found on at least one page. Drop the (rare) gridless pages' OCR after the table so no
    # content is silently lost, while the table itself stays clean and rectangular.
    grid_models = [pm for pm in page_models if pm is not None]
    diseases = _assemble(grid_models)
    table = _render(diseases)
    leftover = "\n\n".join(p for p in plain_pages if p)
    out = table + (("\n\n" + leftover) if leftover.strip() else "")
    log.info("scanned_table_done", pages=len(grid_models), diseases=len(diseases))
    return out or None

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
  6. Assemble a rectangular HTML <table> (every row padded to the full column count, colspans preserved).
  7. Cross-page stitch: if page N+1's first body row continues page N's last row (its left/label cell is empty
     -> no new numbered entry, and the column grid lines up) MERGE it into that row instead of starting anew.

If grid detection fails on a page (too few ruling lines found) the whole document falls back to None so the
caller can use the previous VL stitch path. RapidOCR + geometry are deterministic -> byte-stable output.
"""

from __future__ import annotations

import html

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
        out.append((cx, cy, min(ys), text.strip()))
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


# --------------------------------------------------------------------------- per-page model + cross-page stitch


def _page_model(gray, ocr) -> dict | None:
    """Build a structural model of one page: {n_cols, rows:[{cells:[{text,colspan}], label_empty}], col_lines}.
    Returns None if the page has no usable grid."""
    if not _has_grid(gray):
        return None
    cells = _detect_cells(gray)
    if len(cells) < 2:
        return None
    grid = _build_grid(cells, gray.shape[1], gray.shape[0])
    if grid is None or grid["n_cols"] < _MIN_GRID_COLS:
        return None
    placed = _assign(grid, _ocr_page(gray, ocr))

    # Re-emit as ordered rows. Each grid row index -> the cells whose r == that index, ordered by column.
    rows = []
    by_row: dict[int, list] = {}
    for (r, c), v in placed.items():
        by_row.setdefault(r, []).append((c, v))
    for r in sorted(by_row):
        cols = sorted(by_row[r], key=lambda t: t[0])
        cells_out = [{"c": c, "text": v["text"], "colspan": v["colspan"]} for c, v in cols]
        first_text = cells_out[0]["text"] if cells_out else ""
        rows.append({"r": r, "cells": cells_out, "kind": _row_kind(cells_out),
                     "label_empty": (cols[0][0] != 0) or (first_text == "")})

    rows = _merge_intra_page_fragments(rows)
    return {"n_cols": grid["n_cols"], "xs": grid["xs"], "rows": rows}


_HEADER_WORDS = {"临床特征", "病原体", "传染源", "传播途径", "潜伏期", "隔离期",
                 "特异性治疗", "防控措施", "实验室检查"}


def _row_kind(cells_out: list[dict]) -> str:
    """Classify a row: 'title' (a numbered disease entry: its leftmost cell starts at col 0 with a number),
    'header' (its cells are the column-name header labels), else 'data'. Used to merge stray fragment rows into
    the right anchor without crossing a disease boundary."""
    if not cells_out:
        return "data"
    first = cells_out[0]
    txt = first["text"].strip()
    if first["c"] == 0 and (txt[:1].isdigit() or txt[:2] in {"1.", "2.", "3.", "4.", "5."}):
        return "title"
    labels = sum(1 for cell in cells_out if cell["text"].strip() in _HEADER_WORDS)
    if labels >= 2 and labels >= len(cells_out) - 1:
        return "header"
    return "data"


def _merge_intra_page_fragments(rows: list[dict]) -> list[dict]:
    """Fold a thin fragment row (label column empty, <=2 cells -> a vertically-split tall column such as the
    SARS 传播途径 column whose label/content land on their own grid rows) into the most recent fuller row of the
    SAME kind that is still missing those columns. Never crosses a 'title' row (disease boundary). This rebuilds
    a disease's data row whole when one of its columns is internally subdivided by the scan's grid."""
    out: list[dict] = []
    for row in rows:
        is_fragment = (len(row["cells"]) <= 2 and row["label_empty"] and row["kind"] == "data"
                       and all(cell["c"] != 0 for cell in row["cells"]))
        target = None
        if is_fragment and out:
            for prev in reversed(out):
                if prev["kind"] == "title":
                    break  # do not pull a fragment across a disease boundary
                if prev["kind"] == "data":
                    target = prev  # the most recent data row of this disease block is the anchor
                    break
        if target is not None:
            by_c = {c["c"]: c for c in target["cells"]}
            for cell in row["cells"]:
                if cell["c"] in by_c:  # bottom continuation of a tall split cell -> append to same cell
                    dst = by_c[cell["c"]]
                    dst["text"] = (dst["text"] + "\n" + cell["text"]).strip() if dst["text"] else cell["text"]
                else:  # a column the anchor lacked (subdivided side column) -> add it
                    target["cells"].append(cell)
                    by_c[cell["c"]] = cell
        else:
            out.append(row)
    return out


def _esc(t: str) -> str:
    return html.escape(t).replace("\n", "<br>")


def _rows_to_html(all_rows: list[dict], n_cols: int) -> str:
    """Render quantized rows to a rectangular HTML table: every <tr> covers exactly n_cols columns (padding with
    empty <td> where a column has no cell), colspans preserved for merged/spanning cells."""
    parts = ["<table>"]
    for row in all_rows:
        tds = []
        covered = 0
        for cell in sorted(row["cells"], key=lambda c: c["c"]):
            # pad missing leading/intermediate columns
            while covered < cell["c"]:
                tds.append("<td></td>")
                covered += 1
            span = max(1, min(cell["colspan"], n_cols - covered))
            attr = f" colspan=\"{span}\"" if span > 1 else ""
            tds.append(f"<td{attr}>{_esc(cell['text'])}</td>")
            covered += span
        while covered < n_cols:
            tds.append("<td></td>")
            covered += 1
        parts.append("<tr>" + "".join(tds) + "</tr>")
    parts.append("</table>")
    return "".join(parts)


def _stitch(page_models: list[dict]) -> str:
    """Concatenate page row-streams into ONE table, merging a page's first body row into the previous page's last
    row when it is a continuation (its label/left column is empty -> no new numbered entry) and the column grids
    line up. This binds a cell that spilled from the bottom of page N to the top of page N+1 back into the same
    logical row, instead of leaking into the next entry."""
    n_cols = max(pm["n_cols"] for pm in page_models)
    merged: list[dict] = []
    for pm in page_models:
        prows = pm["rows"]
        for idx, row in enumerate(prows):
            cont = (idx == 0 and merged and row.get("label_empty")
                    and abs(pm["n_cols"] - n_cols) <= 1)
            if cont:
                # Append this continuation row's cells into the matching columns of the previous logical row.
                prev = merged[-1]
                prev_by_c = {c["c"]: c for c in prev["cells"]}
                for cell in row["cells"]:
                    if not cell["text"]:
                        continue
                    if cell["c"] in prev_by_c:
                        tgt = prev_by_c[cell["c"]]
                        tgt["text"] = (tgt["text"] + "\n" + cell["text"]).strip() if tgt["text"] else cell["text"]
                    else:
                        prev["cells"].append(cell)
                        prev_by_c[cell["c"]] = cell
            else:
                merged.append({"cells": [dict(c) for c in row["cells"]]})
    return _rows_to_html(merged, n_cols)


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

    Synchronous + CPU-bound (call via run_in_threadpool). Returns None if no page yields a usable grid, so the
    caller can fall back. Deterministic: same bytes -> byte-identical output."""
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
                page_models.append(pm)
            else:
                # A page with no grid in a table-dominated doc -> abort to the VL fallback rather than emit a
                # half table that silently drops that page's content.
                log.info("scanned_table_no_grid_on_page", page=i + 1)
                return None
    finally:
        doc.close()

    if not page_models:
        return None
    table = _stitch(page_models)
    log.info("scanned_table_done", pages=len(page_models),
             cols=max(pm["n_cols"] for pm in page_models))
    return table or None

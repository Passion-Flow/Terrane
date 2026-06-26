"""Self-developed table structure reconstruction — Stream/clustering, pure geometry, no model.

reconstruct_table(boxes): given the text boxes inside one table region, infer the grid by clustering
  rows (y-overlap bands) and columns (x-edge 1-D clustering), resolve row/col spans by extent overlap,
  and emit HTML. (Camelot "Stream" / ClusterTabNet geometry, implemented as our own code.)
detect_tables(page_boxes): find grid-like clusters on a page (>=2 rows x >=2 aligned columns) so the
  reconstructor knows where tables are. Library-agnostic: operates only on Box, so the upstream PDF
  reader (PyMuPDF today, pypdfium2/pdfplumber later) can be swapped without touching this algorithm.

Honest limits: borderless tables with many-line cells, hierarchical headers or heavy empty cells degrade
(over/under-splitting). Those are the cases a small table model may back up later; the HTML/grid logic
stays ours.
"""

from __future__ import annotations

import html as _html
import statistics

from app.services.parse.structure.box import Box


def _cluster_1d(values: list[float], tol: float) -> list[float]:
    """Agglomerative 1-D clustering -> sorted cluster centers (boundaries merged within tol)."""
    if not values:
        return []
    vs = sorted(values)
    clusters: list[list[float]] = [[vs[0]]]
    for v in vs[1:]:
        if v - clusters[-1][-1] <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [statistics.mean(c) for c in clusters]


def _row_bands(boxes: list[Box], tol: float) -> list[list[Box]]:
    """Group boxes into rows by vertical-overlap / y-center proximity."""
    rows: list[list[Box]] = []
    for b in sorted(boxes, key=lambda x: x.cy):
        placed = False
        for row in rows:
            ry = statistics.mean([x.cy for x in row])
            if abs(b.cy - ry) <= tol:
                row.append(b)
                placed = True
                break
        if not placed:
            rows.append([b])
    return [sorted(r, key=lambda x: x.x0) for r in rows]


def reconstruct_table(boxes: list[Box]) -> str:
    """Reconstruct an HTML table from the text boxes inside one table region."""
    boxes = [b for b in boxes if b.text.strip()]
    if len(boxes) < 2:
        return ""
    med_h = statistics.median([b.h for b in boxes if b.h > 0] or [10.0])
    rows = _row_bands(boxes, tol=med_h * 0.7)
    # column boundaries = clusters of left edges across the whole table
    col_centers = _cluster_1d([b.x0 for b in boxes], tol=med_h * 1.2)
    if len(col_centers) < 2 or len(rows) < 2:
        return ""
    pad = med_h * 0.4

    def start_col(b: Box) -> int:
        return min(range(len(col_centers)), key=lambda i: abs(col_centers[i] - b.x0))

    def colspan(b: Box) -> int:
        # span = number of column anchors that fall inside the cell's x-range (NOT the right-edge column,
        # which over-counts whenever a normal cell is simply wider than the column pitch).
        return max(1, sum(1 for c in col_centers if b.x0 - pad <= c <= b.x1 + pad))

    ncols = len(col_centers)
    out = ["<table>"]
    for row in rows:
        # one cell per starting column (merge boxes that share a start column)
        cells: dict[int, list[Box]] = {}
        for b in row:
            cells.setdefault(start_col(b), []).append(b)
        out.append("<tr>")
        c = 0
        while c < ncols:
            if c in cells:
                cb = sorted(cells[c], key=lambda x: x.x0)
                txt = " ".join(b.text.strip() for b in cb)
                span = max(1, min(colspan(cb[0]), ncols - c))
                attr = f' colspan="{span}"' if span > 1 else ""
                out.append(f"<td{attr}>{_html.escape(txt)}</td>")
                c += span
            else:
                out.append("<td></td>")
                c += 1
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def detect_tables(page_boxes: list[Box]) -> list[list[Box]]:
    """Find grid-like box clusters (>=2 rows that share >=2 aligned columns). Returns lists of region boxes.
    Conservative: only contiguous row runs where each row has >=2 cells aligning to a shared column set."""
    if len(page_boxes) < 4:
        return []
    med_h = statistics.median([b.h for b in page_boxes if b.h > 0] or [10.0])
    rows = _row_bands(page_boxes, tol=med_h * 0.7)
    # candidate rows = rows with >=2 boxes (multi-column)
    regions: list[list[Box]] = []
    run: list[list[Box]] = []

    def flush():
        if len(run) >= 2:
            flat = [b for r in run for b in r]
            cols = _cluster_1d([b.x0 for b in flat], tol=med_h * 1.2)
            med_len = statistics.median([len(b.text) for b in flat] or [0])
            # Guards against mistaking multi-column PROSE for a table:
            #  - a real table is either tall (>=3 rows) or wide (>=3 cols);
            #  - table cells are short tokens, not full-width sentences (median cell text < ~40 chars).
            tall_or_wide = len(run) >= 3 or len(cols) >= 3
            if len(cols) >= 2 and tall_or_wide and med_len < 40:
                regions.append(flat)
        run.clear()

    for r in rows:
        if len(r) >= 2:
            run.append(r)
        else:
            flush()
    flush()
    return regions

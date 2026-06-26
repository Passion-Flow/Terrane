"""Self-developed table structure reconstruction — Stream/clustering, pure geometry, no model.

reconstruct_table(boxes): given the text boxes inside one table region, infer the grid by clustering
  rows (y-overlap bands) and columns (x-edge 1-D clustering), resolve row/col spans by extent overlap,
  and emit HTML. (Camelot "Stream" / ClusterTabNet geometry, implemented as our own code.)
detect_tables(page_boxes): find grid-like clusters on a page (>=2 rows x >=2 aligned columns) so the
  reconstructor knows where tables are. Library-agnostic: operates only on Box, so the upstream PDF
  reader (pdfplumber native text) can be swapped without touching this algorithm.

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
    """Reconstruct an HTML table from the text boxes inside one table region.

    Handles BOTH spans, purely geometrically: colspan = how many column anchors fall inside a cell's x-range;
    rowspan = how many row-band anchors fall inside a cell's y-range (a vertically-merged cell crosses several
    bands). A spanned-over (row, col) position is recorded as occupied so the lower row does NOT emit a phantom
    ``<td>`` for it — mirroring the colspan padding/anchor-count approach on the vertical axis."""
    boxes = [b for b in boxes if b.text.strip()]
    if len(boxes) < 2:
        return ""
    med_h = statistics.median([b.h for b in boxes if b.h > 0] or [10.0])
    # column boundaries = clusters of left edges across the whole table
    col_centers = _cluster_1d([b.x0 for b in boxes], tol=med_h * 1.2)
    # Row bands from TOP edges (y0), not centers: a tall vertically-merged cell shares its row's TOP but has a
    # much lower center, so center-clustering would invent a phantom band for it (over-counting rowspan). Its top
    # aligns with the row it begins in, so y0-clustering yields the true band count + clean per-row anchors.
    band_tops = _cluster_1d([b.y0 for b in boxes], tol=med_h * 0.7)
    if len(col_centers) < 2 or len(band_tops) < 2:
        return ""
    pad = med_h * 0.4
    # Anchor used for the "is this band inside the cell's y-range" test = each band's top edge.
    band_centers = band_tops
    nrows = len(band_centers)

    def start_col(b: Box) -> int:
        return min(range(len(col_centers)), key=lambda i: abs(col_centers[i] - b.x0))

    def start_row(b: Box) -> int:
        # The band a cell BEGINS in = the one whose anchor is nearest the cell's TOP edge. A tall vertically-
        # merged cell must be emitted in its top band (its center sits lower and would mis-cluster otherwise).
        return min(range(nrows), key=lambda i: abs(band_centers[i] - b.y0))

    def colspan(b: Box) -> int:
        # span = number of column anchors that fall inside the cell's x-range (NOT the right-edge column,
        # which over-counts whenever a normal cell is simply wider than the column pitch).
        return max(1, sum(1 for c in col_centers if b.x0 - pad <= c <= b.x1 + pad))

    def rowspan(b: Box, ri: int) -> int:
        # span = number of row-band anchors (from this cell's start band downward) inside the cell's y-range.
        # Same padding approach as colspan; counting only bands at/below ri keeps it a forward (downward) extent.
        return max(1, sum(1 for j in range(ri, nrows) if b.y0 - pad <= band_centers[j] <= b.y1 + pad))

    ncols = len(col_centers)
    # Re-bucket every box into the band it VISUALLY begins in (by top edge), so a tall merged cell is emitted in
    # its top row even though its center clustered lower — then rowspan covers the bands below it.
    band_cells: list[dict[int, list[Box]]] = [{} for _ in range(nrows)]
    for b in boxes:
        band_cells[start_row(b)].setdefault(start_col(b), []).append(b)

    occupied: set[tuple[int, int]] = set()   # (row_index, col_index) covered by a span started in a higher row
    out = ["<table>"]
    for ri in range(nrows):
        cells = band_cells[ri]
        out.append("<tr>")
        c = 0
        while c < ncols:
            if (ri, c) in occupied:        # a rowspan from an earlier row covers this cell -> emit nothing
                c += 1
                continue
            if c in cells:
                cb = sorted(cells[c], key=lambda x: x.x0)
                txt = " ".join(b.text.strip() for b in cb)
                cspan = max(1, min(colspan(cb[0]), ncols - c))
                rspan = max(1, min(rowspan(cb[0], ri), nrows - ri))
                attrs = (f' colspan="{cspan}"' if cspan > 1 else "") + (f' rowspan="{rspan}"' if rspan > 1 else "")
                out.append(f"<td{attrs}>{_html.escape(txt)}</td>")
                if rspan > 1:   # reserve the covered cells in the rows below so they emit no duplicate <td>
                    for dr in range(1, rspan):
                        for dc in range(cspan):
                            occupied.add((ri + dr, c + dc))
                c += cspan
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

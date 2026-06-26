"""Self-developed table structure reconstruction — Stream/clustering, pure geometry, no model.

reconstruct_table(boxes): given the text boxes inside one table region, infer the grid by clustering
  rows (y-overlap bands) and columns (x-edge 1-D clustering), resolve row/col spans by extent overlap,
  and emit HTML. (Camelot "Stream" / ClusterTabNet geometry, implemented as our own code.)
detect_tables(page_boxes, geometry): find grid-like clusters on a page (>=2 rows x >=2 aligned columns)
  AND prove each candidate is a REAL table (not a diagram) before returning it. Library-agnostic: operates
  only on Box (+ an optional plain-tuple RulingGeometry), so the upstream PDF reader (pdfplumber native
  text) can be swapped without touching this algorithm.

The real-table GUARD (P0, roadmap §3.1 step 1 / G1+G5): spatial box-alignment alone CANNOT tell a table
from a diagram — a block/circuit/pin diagram or packaging artwork has text labels that cluster into a
pseudo-grid and would otherwise be folded into a garbled <table>, asserting row/col structure that does
not exist. "Asserting false structure is worse than dropping": a candidate is folded into a table ONLY
when it has real table evidence —
  (A) RULING-LINE GRID: full-width horizontal rules form row separators AND there is vertical ruling/anchor
      structure (real cells bounded by vector lines/rects), OR
  (B) REGULAR COLUMN GRID (borderless): enough rows align to a small, STABLE set of column positions (a
      high modal-column-count fraction, >=2 cols x >=3 rows) with low x-deviation,
AND in either case the region is NOT contaminated by vector curves (connectors/illustration strokes — the
hallmark of a diagram, never of a table). When neither holds, the boxes are NOT folded; they fall back to
normal reading-order text flow (the un-folded labels still get indexed as flowing text — acceptable for P0;
figure crop+caption is a later task). Bias is toward NOT emitting a table when ambiguous.

Honest limits: borderless tables with many-line cells, hierarchical headers or heavy empty cells degrade
(over/under-splitting). Those are the cases a small table model may back up later; the HTML/grid logic
stays ours.
"""

from __future__ import annotations

import html as _html
import statistics
from collections import Counter
from dataclasses import dataclass, field

from app.services.parse.structure.box import Box


# --------------------------------------------------------------------------------------------------
# Real vector ruling geometry (threaded in from the PDF reader) — the strong "this IS a table" signal.
# Kept as plain tuples so tables.py stays library-agnostic: engine.py builds this from a pdfplumber page
# (page.lines / page.rects / page.curves), but any reader that can yield the same primitives works.
# --------------------------------------------------------------------------------------------------
@dataclass
class RulingGeometry:
    """Vector ruling lines + curve bboxes for ONE page (top-origin y, page points).

    hlines: horizontal rules  (y, x0, x1)      — rule levels that separate ROWS
    vlines: vertical rules     (x, y0, y1)      — rule levels that separate COLUMNS
    curves: curve bounding boxes (x0, y0, x1, y1) — bezier/spline strokes = diagram connectors/art, NEVER
            part of a real table; their presence inside a candidate region is the diagram tell.
    Built from page.lines + page.rects (each rect contributes its 4 edges as rules) + page.curves.
    """

    hlines: list[tuple[float, float, float]] = field(default_factory=list)
    vlines: list[tuple[float, float, float]] = field(default_factory=list)
    curves: list[tuple[float, float, float, float]] = field(default_factory=list)


# rule-edge thresholds (a ruling is "horizontal" if it is near-flat and long enough to matter, etc.)
_RULE_FLAT = 2.0        # max thickness (pt) for a segment to count as a single H/V rule
_RULE_MIN_LEN = 8.0     # min length (pt) for a segment to count as a rule (filters dots/ticks)


def ruling_geometry(lines: list[dict], rects: list[dict], curves: list[dict]) -> RulingGeometry:
    """Build a RulingGeometry from pdfplumber-style line/rect/curve dicts (keys x0,top,x1,bottom).

    Lives here (not in the reader) so the line/rect -> H/V-rule reduction is part of the table algorithm
    and shared by detection. Each rect contributes its 4 edges as candidate rules — a ruled table drawn as
    a stack of rects (reportlab `canvas.rect` per cell, or boxed register tables) is thereby recognized."""
    H: list[tuple[float, float, float]] = []
    V: list[tuple[float, float, float]] = []
    for ln in lines:
        x0, y0, x1, y1 = ln["x0"], ln["top"], ln["x1"], ln["bottom"]
        if abs(y0 - y1) <= _RULE_FLAT and abs(x0 - x1) > _RULE_MIN_LEN:
            H.append((y0, min(x0, x1), max(x0, x1)))
        elif abs(x0 - x1) <= _RULE_FLAT and abs(y0 - y1) > _RULE_MIN_LEN:
            V.append((x0, min(y0, y1), max(y0, y1)))
    for r in rects:
        x0, y0, x1, y1 = r["x0"], r["top"], r["x1"], r["bottom"]
        if x1 - x0 > _RULE_MIN_LEN:
            H += [(y0, x0, x1), (y1, x0, x1)]
        if y1 - y0 > _RULE_MIN_LEN:
            V += [(x0, y0, y1), (x1, y0, y1)]
    C = [(c["x0"], c["top"], c["x1"], c["bottom"]) for c in curves]
    return RulingGeometry(hlines=H, vlines=V, curves=C)


def _region_bbox(reg: list[Box]) -> tuple[float, float, float, float]:
    return (min(b.x0 for b in reg), min(b.y0 for b in reg),
            max(b.x1 for b in reg), max(b.y1 for b in reg))


def _spanning_rule_levels(rules: list[tuple[float, float, float]], lo: float, hi: float,
                          span_lo: float, span_hi: float, frac: float) -> int:
    """Count DISTINCT rule levels (clustered to within 3pt) that lie within [lo,hi] (the region's range on
    the rule's normal axis) and span >= `frac` of [span_lo, span_hi] (the region's extent along the rule).

    For horizontal rules: lo/hi = region y-range, span = region width -> counts full-width ROW separators.
    For vertical rules:   lo/hi = region x-range, span = region height -> counts full-height COL separators.
    A real ruled table has multiple such region-spanning rules; a diagram's box edges are short and local."""
    span = span_hi - span_lo
    if span <= 0:
        return 0
    levels = [p for p, a, b in rules
              if lo - 3 <= p <= hi + 3 and (min(b, span_hi) - max(a, span_lo)) >= frac * span]
    if not levels:
        return 0
    levels.sort()
    n, last = 1, levels[0]
    for v in levels[1:]:
        if v - last > 3:
            n += 1
        last = v
    return n


def _curves_inside(curves: list[tuple[float, float, float, float]],
                   bbox: tuple[float, float, float, float]) -> int:
    """Number of vector curves whose bbox overlaps the region — diagram connectors / illustration strokes."""
    rx0, ry0, rx1, ry1 = bbox
    return sum(1 for cx0, cy0, cx1, cy1 in curves
               if not (cx1 < rx0 or cx0 > rx1 or cy1 < ry0 or cy0 > ry1))


# Guard thresholds (calibrated on real docs: UMS9620 chip spec, S63AR packaging, reportlab digital set).
_GRID_MODAL_FRAC = 0.75   # >= this fraction of multi-cell rows must share the SAME column count (stable grid)
_GRID_MIN_ROWS = 3        # need several rows to call it a regular column grid (2 rows is too weak)
_COL_DEV_MAX = 0.6        # median |cell.x0 - nearest column anchor| / line-height: low => cells truly align
_CURVE_TOLERANCE = 2      # > this many curves inside a region => treat as diagram, never fold (connectors)


def _is_real_table(reg: list[Box], geometry: RulingGeometry | None, med_h: float) -> bool:
    """Discriminate a REAL table from a diagram/artwork label-cloud. Fold ONLY if (ruling grid) OR
    (regular borderless column grid), and NEVER if vector curves contaminate the region (a diagram tell).

    With no geometry threaded in, the curve veto and ruling path are unavailable, so the decision rests on
    the column-regularity path alone (still strictly better than the old no-check behavior)."""
    bbox = _region_bbox(reg)
    rx0, ry0, rx1, ry1 = bbox

    # (0) Curve veto: bezier/spline strokes inside the region = connectors/illustration -> it is a DIAGRAM,
    # not a table. A genuine ruled/borderless table contains no curves. This alone kills block diagrams and
    # packaging artwork (which are curve-saturated) even when their labels happen to pseudo-align.
    if geometry is not None and _curves_inside(geometry.curves, bbox) > _CURVE_TOLERANCE:
        return False

    # (A) RULING-LINE GRID: full-width horizontal rules forming row separators, plus vertical structure
    # (full-height vertical rules OR — for column-ruled-only tables — >=2 column anchors). Evidence that
    # vector lines bound real cells.
    has_ruling_grid = False
    if geometry is not None:
        h_levels = _spanning_rule_levels(geometry.hlines, ry0, ry1, rx0, rx1, frac=0.55)
        v_levels = _spanning_rule_levels(geometry.vlines, rx0, rx1, ry0, ry1, frac=0.55)
        col_anchors = len(_cluster_1d([b.x0 for b in reg], tol=med_h * 1.2))
        # a real ruled table: >=2 row-separating rules AND (>=2 col rules OR >=2 aligned col anchors)
        if h_levels >= 2 and (v_levels >= 2 or col_anchors >= 2):
            has_ruling_grid = True
        # or a fully boxed grid: >=2 col rules AND >=2 aligned column anchors AND >=1 row rule
        elif v_levels >= 2 and h_levels >= 1 and col_anchors >= 2:
            has_ruling_grid = True
    if has_ruling_grid:
        return True

    # (B) REGULAR (borderless) COLUMN GRID: many rows aligning to a stable, small set of column positions.
    # Diagrams have scattered, irregular box positions whose per-row column counts vary wildly; a real
    # borderless table has a near-constant column count and cells that snap tightly to shared anchors.
    rows = _row_bands(reg, tol=med_h * 0.7)
    multirows = [r for r in rows if len(r) >= 2]
    if len(multirows) < _GRID_MIN_ROWS:
        return False
    counts = [len(r) for r in multirows]
    modal_cols, modal_n = Counter(counts).most_common(1)[0]
    if modal_cols < 2:
        return False
    modal_frac = modal_n / len(multirows)
    col_anchors = _cluster_1d([b.x0 for b in reg], tol=med_h * 1.2)
    if not col_anchors:
        return False
    devs = [min(abs(c - b.x0) for c in col_anchors) for b in reg]
    col_dev_norm = (statistics.median(devs) / med_h) if med_h > 0 else 1.0
    if modal_frac < _GRID_MODAL_FRAC or col_dev_norm > _COL_DEV_MAX:
        return False
    # A BULLETED/NUMBERED LIST pseudo-aligns into a 2-column grid (marker glyph + long prose line) and would
    # otherwise be asserted as a borderless table. Reject the degenerate "one tiny-marker column + one long-
    # prose column" shape: a real 2-column table's columns both carry real tokens, not a 1-char marker beside
    # a sentence. (Only checked for the 2-anchor case; wider grids are genuine tables.)
    if not _is_marker_list(reg, col_anchors):
        return True
    return False


def _is_marker_list(reg: list[Box], col_anchors: list[float]) -> bool:
    """True if `reg` is a marker+prose LIST disguised as a 2-column table: exactly two column anchors, one of
    which holds only tiny markers (every cell <=2 chars — a bullet glyph / list ordinal) while the other holds
    long prose (median cell length >= a sentence-ish width). Such a region is flowing list text, not a table."""
    if len(col_anchors) != 2:
        return False
    cols: list[list[Box]] = [[], []]
    for b in reg:
        ci = 0 if abs(col_anchors[0] - b.x0) <= abs(col_anchors[1] - b.x0) else 1
        cols[ci].append(b)
    if not cols[0] or not cols[1]:
        return False

    def max_len(c: list[Box]) -> int:
        return max(len(b.text.strip()) for b in c)

    def med_len(c: list[Box]) -> float:
        return statistics.median([len(b.text.strip()) for b in c])

    marker = any(max_len(c) <= 2 for c in cols)              # a column that is ALL <=2-char markers
    prose = any(med_len(c) >= 28 for c in cols)              # a column of sentence-length cells
    return marker and prose


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


def detect_tables(page_boxes: list[Box], geometry: RulingGeometry | None = None) -> list[list[Box]]:
    """Find grid-like box clusters that are REAL tables (not diagrams). Returns lists of region boxes.

    Two-stage: (1) cluster contiguous multi-column row runs into candidate regions (the original spatial
    pre-filter — prose guard: tall-or-wide, short cells), then (2) keep ONLY candidates that pass the
    real-table GUARD (`_is_real_table`): a ruling-line grid OR a regular borderless column grid, never a
    curve-contaminated diagram. `geometry` (vector rules + curves from the PDF reader) is what lets the
    guard distinguish a block/circuit/pin diagram or packaging artwork — whose labels pseudo-align into a
    grid — from a genuine table; without it, only the column-regularity half of the guard applies."""
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
            if len(cols) >= 2 and tall_or_wide and med_len < 40 and _is_real_table(flat, geometry, med_h):
                regions.append(flat)
        run.clear()

    for r in rows:
        if len(r) >= 2:
            run.append(r)
        else:
            flush()
    flush()
    return regions

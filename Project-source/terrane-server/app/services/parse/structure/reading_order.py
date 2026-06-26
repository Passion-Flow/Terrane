"""Self-developed reading-order detection — XY-Cut++ (arXiv:2504.10258), pure geometry, no model.

Plain recursive XY-cut fails on cross-column elements (a banner/title/wide table that bridges two
columns has no clean projection valley, so the cut is wrong). XY-Cut++ fixes this in four stages:

  1. Pre-mask: temporarily remove "spanning" elements (long boxes overlapping >=2 others) so they stop
     gluing columns together.
  2. Density-adaptive recursive cut: choose cut axis by column-vs-row whitespace density, not always
     horizontal-first; emit boxes in cut-tree pre-order (the reading order of the remaining boxes).
  3. Re-insertion: place each masked element back next to the already-ordered box it is geometrically
     closest to (label-priority: cross-layout > title > vision > other).
  4. Stable final order.

CPU-trivial (O(N log N)-ish), hundreds of FPS. Reference plain XY-cut: Nagy et al. ICPR'84.
"""

from __future__ import annotations

import statistics

from app.services.parse.structure.box import Box

_SPAN_BETA = 1.3          # spanning threshold = beta * median(box longer-side)
_DENSITY_TAU = 0.9        # column/row density ratio above which we cut horizontally first
_LABEL_PRIORITY = {"cross": 0, "title": 1, "figure": 2, "vision": 2, "table": 1, "formula": 2}


def _gap_threshold(boxes: list[Box], axis: int) -> float:
    """Minimum valley width to accept a cut. Both column gutters and line gaps scale with text height,
    so we use the median box height (≈ line height) as the unit for either axis. (Using box *width*
    would set the column-split threshold absurdly high and miss real gutters.)"""
    if len(boxes) < 2:
        return 1.0
    med_h = statistics.median([b.h for b in boxes if b.h > 0] or [1.0])
    return max(3.0, med_h * 0.6)


def _find_valleys(boxes: list[Box], axis: int) -> list[tuple[float, float]]:
    """Find full-span empty gaps along an axis (axis=0: vertical cut lines x; axis=1: horizontal y).
    Returns sorted [(start, end)] intervals of the cut coordinate that no box overlaps."""
    if axis == 0:
        intervals = sorted((b.x0, b.x1) for b in boxes)
        lo = min(b.x0 for b in boxes)
        hi = max(b.x1 for b in boxes)
    else:
        intervals = sorted((b.y0, b.y1) for b in boxes)
        lo = min(b.y0 for b in boxes)
        hi = max(b.y1 for b in boxes)
    valleys: list[tuple[float, float]] = []
    cursor = lo
    for s, e in intervals:
        if s > cursor:
            valleys.append((cursor, s))   # empty band [cursor, s]
        cursor = max(cursor, e)
    _ = hi
    return valleys


def _density_axis(boxes: list[Box]) -> int:
    """Pick cut axis by whitespace density. Returns 0 (vertical cut = split columns) or 1 (horizontal)."""
    if len(boxes) < 2:
        return 1
    col_valleys = _find_valleys(boxes, 0)
    row_valleys = _find_valleys(boxes, 1)
    col_gap = sum(e - s for s, e in col_valleys)
    row_gap = sum(e - s for s, e in row_valleys)
    # if column gutters dominate -> there are columns -> split vertically (axis 0) first
    tau = col_gap / (row_gap + 1e-6)
    return 0 if tau > _DENSITY_TAU else 1


def _xy_cut(boxes: list[Box], axis: int | None, out: list[Box], depth: int = 0) -> None:
    """Recursive XY-cut. Emits boxes into `out` in reading order (pre-order of the cut tree)."""
    if len(boxes) <= 1:
        out.extend(boxes)
        return
    if depth > 64:  # safety
        out.extend(sorted(boxes, key=lambda b: (b.y0, b.x0)))
        return
    if axis is None:
        axis = _density_axis(boxes)

    valleys = [v for v in _find_valleys(boxes, axis) if (v[1] - v[0]) >= _gap_threshold(boxes, axis)]
    if not valleys:
        # cannot cut this axis -> try the other once; if neither cuts, fall back to raster order
        other = _find_valleys(boxes, 1 - axis)
        other = [v for v in other if (v[1] - v[0]) >= _gap_threshold(boxes, 1 - axis)]
        if not other:
            out.extend(sorted(boxes, key=lambda b: (b.y0, b.x0)))
            return
        return _xy_cut(boxes, 1 - axis, out, depth + 1)

    # split into ordered slices at every qualifying valley
    cuts = sorted(((v[0] + v[1]) / 2.0) for v in valleys)
    slices: list[list[Box]] = [[] for _ in range(len(cuts) + 1)]
    for b in boxes:
        coord = b.cx if axis == 0 else b.cy
        idx = 0
        while idx < len(cuts) and coord > cuts[idx]:
            idx += 1
        slices[idx].append(b)
    # reading order: left->right for vertical cut (columns), top->bottom for horizontal cut
    for sl in slices:
        if sl:
            _xy_cut(sl, 1 - axis, out, depth + 1)


def _column_gutters(boxes: list[Box]) -> list[tuple[float, float]]:
    """Vertical whitespace gutters (column separators) formed by the given boxes."""
    if len(boxes) < 2:
        return []
    return [v for v in _find_valleys(boxes, 0) if (v[1] - v[0]) >= _gap_threshold(boxes, 0)]


def _is_spanning(b: Box, gutters: list[tuple[float, float]], span_len: float) -> bool:
    """Spanning = long AND it *bridges a real column gutter* (so removing it lets the columns split).
    This is the correct criterion: a wide body line in a single-column page has no gutter to bridge,
    so it is NOT flagged (the earlier 'overlaps >=2 boxes' rule wrongly masked single-column body text)."""
    if b.w < span_len or not gutters:
        return False
    return any(b.x0 < gs and b.x1 > ge for gs, ge in gutters)


def _label_rank(b: Box) -> int:
    if b.label in ("title",) or b.meta.get("spanning"):
        return _LABEL_PRIORITY.get("cross" if b.meta.get("spanning") else "title", 1)
    return _LABEL_PRIORITY.get(b.label, 3)


def reading_order(boxes: list[Box]) -> list[Box]:
    """Return the boxes in human reading order (XY-Cut++). Stable, deterministic, no model."""
    boxes = [b for b in boxes if b.w > 0 and b.h > 0]
    if len(boxes) <= 1:
        return list(boxes)

    # Stage 1: pre-mask spanning elements.
    # Gutters are computed from the NARROW boxes only — a wide spanning title would otherwise fill the
    # gutter and hide the column structure. A box is masked only if it bridges one of those gutters.
    span_len = _SPAN_BETA * statistics.median([b.w for b in boxes] or [1.0])
    narrow = [b for b in boxes if b.w <= span_len]
    gutters = _column_gutters(narrow if len(narrow) >= 2 else boxes)
    masked: list[Box] = []
    body: list[Box] = []
    for b in boxes:
        if _is_spanning(b, gutters, span_len):
            b.meta["spanning"] = True
            masked.append(b)
        else:
            body.append(b)

    # Stage 2: density-adaptive recursive cut on the body
    ordered: list[Box] = []
    _xy_cut(body or boxes, None, ordered)

    if not masked:
        return ordered

    # Stage 3: re-insert masked elements next to the closest already-ordered box, by label priority
    for m in sorted(masked, key=_label_rank):
        best_pos, best_d = len(ordered), float("inf")
        for i, o in enumerate(ordered):
            # weighted geometric distance: prefer same column + vertical adjacency
            dx = abs(o.cx - m.cx)
            dy = abs(o.cy - m.cy)
            d = dy + 0.3 * dx + (0 if (o.x0 < m.x1 and o.x1 > m.x0) else max(m.w, o.w))
            # insert above the box if the spanning element sits above it
            cand_pos = i if m.cy <= o.cy else i + 1
            if d < best_d:
                best_d, best_pos = d, cand_pos
        ordered.insert(best_pos, m)

    return ordered

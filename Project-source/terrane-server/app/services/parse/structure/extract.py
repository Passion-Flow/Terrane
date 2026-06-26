"""Extract recognizer boxes from a PDF's native text layer (pdfplumber) — free, exact, no OCR.

For digital PDFs this gives precise text + font_size + bold per line, which feeds the self-developed
structure engine (reading order + hierarchy) with zero recognition error and zero model cost. Scanned
PDFs (no extractable text) yield few/no boxes -> caller falls back to the VL/OCR path.
"""

from __future__ import annotations

import io
import statistics

from app.services.parse.structure.box import Box

_LINE_TOL = 3.0  # words whose `top` differ by less than this belong to the same text line


def _is_bold(word: dict) -> bool:
    return "bold" in (word.get("fontname", "") or "").lower()


def extract_page_boxes(page) -> list[Box]:
    """One Box per text line (good granularity for both reading order and heading detection).

    `page` is a pdfplumber Page; words are grouped into lines by clustering on their top coordinate.
    """
    try:
        words = page.extract_words(extra_attrs=["size", "fontname"])
    except Exception:  # noqa: BLE001
        return []
    words = [w for w in words if (w.get("text") or "").strip()]
    if not words:
        return []

    # Group words into lines: sort by top, then x, and cluster consecutive words whose `top` is close.
    words.sort(key=lambda w: (round(float(w.get("top", 0.0)), 1), float(w.get("x0", 0.0))))
    lines: list[list[dict]] = []
    for w in words:
        top = float(w.get("top", 0.0))
        if lines and abs(top - float(lines[-1][0].get("top", 0.0))) <= _LINE_TOL:
            lines[-1].append(w)
        else:
            lines.append([w])

    boxes: list[Box] = []
    bid = 0
    for line in lines:
        line.sort(key=lambda w: float(w.get("x0", 0.0)))
        # Split a line into segments at large horizontal gaps so table cells become separate boxes
        # (extract_words merges cells separated by small gaps, so we re-introduce the split on big
        # inter-word gaps to keep the downstream table detection working).
        for seg in _split_line_segments(line):
            text = " ".join((w.get("text") or "") for w in seg).strip()
            if not text:
                continue
            xs0 = [float(w["x0"]) for w in seg]
            ys0 = [float(w["top"]) for w in seg]
            xs1 = [float(w["x1"]) for w in seg]
            ys1 = [float(w["bottom"]) for w in seg]
            size = statistics.median([float(w.get("size", 0) or 0) for w in seg]) or 0.0
            bold_chars = sum(len(w.get("text") or "") for w in seg if _is_bold(w))
            boxes.append(Box(id=bid, x0=min(xs0), y0=min(ys0), x1=max(xs1), y1=max(ys1),
                             text=text, font_size=size, bold=(bold_chars > 0.5 * len(text))))
            bid += 1
    return boxes


def _split_line_segments(line: list[dict]) -> list[list[dict]]:
    """Split one text line (sorted by x0) into segments wherever a wide horizontal gap separates words.

    A normal inter-word space is ~0.3x the font size; a table-cell gap is much wider. Splitting on gaps
    > ~1.5x the local font size recovers the per-cell granularity that table detection relies on, while
    leaving ordinary prose lines as a single segment."""
    if len(line) <= 1:
        return [line]
    segs: list[list[dict]] = [[line[0]]]
    for w in line[1:]:
        prev = segs[-1][-1]
        gap = float(w.get("x0", 0.0)) - float(prev.get("x1", 0.0))
        sz = float(w.get("size", 0) or prev.get("size", 0) or 10.0)
        if gap > sz * 1.5:
            segs.append([w])
        else:
            segs[-1].append(w)
    return segs


def has_text_layer(pdf_bytes: bytes, min_chars: int = 80) -> bool:
    """True if the PDF has enough extractable native text to use the structure engine (vs scanned).
    Truly scanned (no-OCR) PDFs extract ~0 chars; any digital page clears a low threshold."""
    try:
        import pdfplumber
        pl = pdfplumber.open(io.BytesIO(pdf_bytes))
    except Exception:  # noqa: BLE001
        return False
    chars = 0
    try:
        for page in pl.pages:
            chars += len((page.extract_text() or "").strip())
            if chars >= min_chars:
                return True
    finally:
        pl.close()
    return False

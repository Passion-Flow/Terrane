"""Extract recognizer boxes from a PDF's native text layer (PyMuPDF) — free, exact, no OCR.

For digital PDFs this gives precise text + font_size + bold per line, which feeds the self-developed
structure engine (reading order + hierarchy) with zero recognition error and zero model cost. Scanned
PDFs (no extractable text) yield few/no boxes -> caller falls back to the VL/OCR path.
"""

from __future__ import annotations

import statistics

from app.services.parse.structure.box import Box

_BOLD_FLAG = 1 << 4  # PyMuPDF span flag bit 4 = bold


def _is_bold(span: dict) -> bool:
    return bool(span.get("flags", 0) & _BOLD_FLAG) or "bold" in (span.get("font", "") or "").lower()


def extract_page_boxes(page) -> list[Box]:
    """One Box per text line (good granularity for both reading order and heading detection)."""
    try:
        d = page.get_text("dict")
    except Exception:  # noqa: BLE001
        return []
    boxes: list[Box] = []
    bid = 0
    for block in d.get("blocks", []):
        if block.get("type") != 0:  # 0 = text block
            continue
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if (s.get("text") or "").strip()]
            if not spans:
                continue
            text = "".join(s["text"] for s in spans).strip()
            if not text:
                continue
            xs0 = [s["bbox"][0] for s in spans]
            ys0 = [s["bbox"][1] for s in spans]
            xs1 = [s["bbox"][2] for s in spans]
            ys1 = [s["bbox"][3] for s in spans]
            size = statistics.median([float(s.get("size", 0)) for s in spans]) or 0.0
            bold_chars = sum(len(s["text"]) for s in spans if _is_bold(s))
            boxes.append(Box(id=bid, x0=min(xs0), y0=min(ys0), x1=max(xs1), y1=max(ys1),
                             text=text, font_size=size, bold=(bold_chars > 0.5 * len(text))))
            bid += 1
    return boxes


def has_text_layer(pdf_bytes: bytes, min_chars: int = 80) -> bool:
    """True if the PDF has enough extractable native text to use the structure engine (vs scanned).
    Truly scanned (no-OCR) PDFs extract ~0 chars; any digital page clears a low threshold."""
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:  # noqa: BLE001
        return False
    chars = 0
    for page in doc:
        chars += len((page.get_text("text") or "").strip())
        if chars >= min_chars:
            return True
    return False

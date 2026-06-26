"""Per-page document router — classify EACH PDF page and send it to the precise handler for its class.

The precision rule (design/10-precise-parsing-engine.md §2, roadmap task #1): routing must be **per page**,
not per document. A digital (text-layer) page carries exact native characters/coordinates/fonts, so it must go
through the self-developed structure engine (near-0 character error) and must NEVER be re-OCR'd by the vision
model (measured VL text acc ~0.78 vs ~1.0 from the native layer). A scanned page inside a digital PDF (or vice
versa) must be routed on its own merits, so a mixed PDF is parsed page-by-page.

This module is pure routing + deterministic feature extraction. It does NOT call the model; the caller
(`_parse_by_tier`) uses the classification to assemble the per-page handlers (structure engine for digital
pages, the CV scanned-table path for ruled scanned pages, VL/per-page OCR for gridless scanned prose).

Determinism: features come from pdfplumber native text (free, exact) and — only for pages that lack a text
layer — a single low-DPI bitmap render fed to the existing `_bitmap_has_grid` run detector. Same bytes ->
same classification, no model, no sampling.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import structlog

log = structlog.get_logger("terrane.parse.router")

# A page with at least this many extractable native characters is treated as DIGITAL (text-layer present), so
# it goes to the structure engine. Matches the per-document threshold the scanned-vs-digital detectors already
# use (`vl._SCANNED_TEXT_MIN` = 24) — low enough that a sparse but genuine text page (a section divider, a
# mostly-figure page with a caption) still routes digital, high enough that OCR noise / stray glyphs don't.
TEXT_MIN = 24

# Page classes (the handler each page is routed to).
DIGITAL = "digital"            # text layer -> structure engine (exact native text, 0 recognition error)
SCANNED_TABLE = "scanned_table"  # no text layer + ruling-line grid -> scanned_table.py (deterministic CV)
SCANNED_PROSE = "scanned_prose"  # no text layer, no grid -> VL / per-page OCR


@dataclass
class PageFeatures:
    """Deterministic per-page feature vector + the class it routes to."""

    page_no: int                 # 1-indexed
    text_chars: int = 0          # extractable native characters (text-layer signal)
    vector_lines: int = 0        # page.lines + page.rects count (digital ruled-table hint)
    has_bitmap_grid: bool = False  # long horizontal+vertical raster ruling runs (scanned ruled table)
    cls: str = SCANNED_PROSE     # routed class


@dataclass
class RouteResult:
    """Per-page classification for a whole PDF."""

    pages: list[PageFeatures] = field(default_factory=list)

    @property
    def digital_pages(self) -> set[int]:
        return {p.page_no for p in self.pages if p.cls == DIGITAL}

    @property
    def scanned_table_pages(self) -> set[int]:
        return {p.page_no for p in self.pages if p.cls == SCANNED_TABLE}

    @property
    def scanned_prose_pages(self) -> set[int]:
        return {p.page_no for p in self.pages if p.cls == SCANNED_PROSE}

    @property
    def all_digital(self) -> bool:
        return bool(self.pages) and all(p.cls == DIGITAL for p in self.pages)

    @property
    def any_digital(self) -> bool:
        return any(p.cls == DIGITAL for p in self.pages)

    @property
    def any_scanned(self) -> bool:
        return any(p.cls != DIGITAL for p in self.pages)


def route_pdf(pdf_bytes: bytes) -> RouteResult:
    """Classify every page of a PDF deterministically. Empty result on open failure (caller falls back).

    Decision order (short-circuit, first match wins):
      1. text_chars >= TEXT_MIN          -> DIGITAL          (text layer: prefer the 0-error structure engine)
      2. no text layer + bitmap grid     -> SCANNED_TABLE    (CV ruling grid -> scanned_table.py)
      3. no text layer, no grid          -> SCANNED_PROSE    (VL / per-page OCR)
    The bitmap grid check renders ONLY pages that lack a text layer (digital pages never get rasterized), at
    low DPI, so the cost is bounded and the structure engine's pages stay model-free.
    """
    try:
        import pdfplumber
    except Exception as e:  # noqa: BLE001
        log.warning("router_pdfplumber_import_failed", error=str(e))
        return RouteResult()
    try:
        pl = pdfplumber.open(io.BytesIO(pdf_bytes))
    except Exception as e:  # noqa: BLE001
        log.warning("router_open_failed", error=str(e))
        return RouteResult()

    feats: list[PageFeatures] = []
    scanned_idx: list[int] = []  # 0-indexed pages needing a bitmap-grid check
    try:
        for pno, page in enumerate(pl.pages, start=1):
            try:
                chars = len((page.extract_text() or "").strip())
            except Exception:  # noqa: BLE001
                chars = 0
            try:
                vlines = len(page.lines) + len(page.rects)
            except Exception:  # noqa: BLE001
                vlines = 0
            pf = PageFeatures(page_no=pno, text_chars=chars, vector_lines=vlines)
            if chars >= TEXT_MIN:
                pf.cls = DIGITAL  # text layer present -> structure engine, never VL-OCR
            else:
                scanned_idx.append(pno - 1)  # defer: needs a render to decide table vs prose
            feats.append(pf)
            # Release this page's cached parse so routing a 450-page PDF stays memory-bounded (pdfplumber retains
            # every visited page's objects on the PDF otherwise — the dominant peak before this fix).
            try:
                page.flush_cache()
                page.close()
            except Exception:  # noqa: BLE001
                pass
    finally:
        pl.close()

    # Only render the no-text-layer pages, once, at low DPI, to look for a ruled-table grid.
    if scanned_idx:
        _classify_scanned_pages(pdf_bytes, feats, scanned_idx)

    res = RouteResult(pages=feats)
    log.info("route_pdf_done", pages=len(feats), digital=len(res.digital_pages),
             scanned_table=len(res.scanned_table_pages), scanned_prose=len(res.scanned_prose_pages))
    return res


def _classify_scanned_pages(pdf_bytes: bytes, feats: list[PageFeatures], scanned_idx: list[int]) -> None:
    """For each no-text-layer page, render a low-DPI bitmap and detect a ruling grid -> SCANNED_TABLE else
    SCANNED_PROSE. Reuses `vl._bitmap_has_grid` (the same detector the per-document path used). On any failure
    the page stays SCANNED_PROSE (safe: it goes to per-page OCR rather than the table path)."""
    try:
        import pypdfium2 as pdfium

        from app.services.parse.vl import _bitmap_has_grid
    except Exception as e:  # noqa: BLE001
        log.warning("router_render_import_failed", error=str(e))
        return
    try:
        doc = pdfium.PdfDocument(pdf_bytes)
    except Exception as e:  # noqa: BLE001
        log.warning("router_pdfium_open_failed", error=str(e))
        return
    by_no = {pf.page_no: pf for pf in feats}
    try:
        npages = len(doc)
        for idx in scanned_idx:
            if idx >= npages:
                continue
            page = doc[idx]
            try:
                pil = page.render(scale=100 / 72.0).to_pil()  # low DPI is enough to find ruling lines
            except Exception:  # noqa: BLE001
                continue
            finally:
                page.close()
            pf = by_no.get(idx + 1)
            if pf is None:
                continue
            try:
                pf.has_bitmap_grid = bool(_bitmap_has_grid(pil))
            except Exception:  # noqa: BLE001
                pf.has_bitmap_grid = False
            pf.cls = SCANNED_TABLE if pf.has_bitmap_grid else SCANNED_PROSE
    finally:
        doc.close()


def subset_pdf(pdf_bytes: bytes, pages: set[int]) -> bytes | None:
    """Return a new PDF containing only `pages` (1-indexed), in order — for handing a per-page subset to a
    whole-document handler (the CV scanned-table path / VL path operate on a PDF, not a page list). Returns
    None on failure or empty selection. Deterministic (pypdfium2 page copy; preserves text layer, no re-render)."""
    if not pages:
        return None
    try:
        import pypdfium2 as pdfium
    except Exception as e:  # noqa: BLE001
        log.warning("router_pdfium_import_failed", error=str(e))
        return None
    src = None
    dst = None
    try:
        src = pdfium.PdfDocument(pdf_bytes)
        n = len(src)
        idxs = [pno - 1 for pno in sorted(pages) if 1 <= pno <= n]
        if not idxs:
            return None
        dst = pdfium.PdfDocument.new()
        dst.import_pages(src, idxs)
        buf = io.BytesIO()
        dst.save(buf)
        return buf.getvalue()
    except Exception as e:  # noqa: BLE001
        log.warning("router_subset_failed", error=str(e))
        return None
    finally:
        try:
            if dst is not None:
                dst.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            if src is not None:
                src.close()
        except Exception:  # noqa: BLE001
            pass

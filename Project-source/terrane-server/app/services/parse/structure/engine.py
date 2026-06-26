"""Structure engine orchestrator — PDF bytes -> reading-ordered, hierarchical structured Markdown.

Ties together: native box extraction (per page) -> XY-Cut++ reading order (per page) -> cross-page
font/numbering hierarchy -> Markdown with `#` headings and `<!-- Page N -->` markers. The emitted
Markdown is exact native text (no OCR error) and carries the structure, so the existing tree builder
and chunker stay consistent. Returns None when the PDF has no usable text layer (caller -> VL/OCR).
"""

from __future__ import annotations

import io
import re

import structlog

from app.services.parse.structure.box import Box
from app.services.parse.structure.extract import extract_page_boxes, has_text_layer
from app.services.parse.structure.hierarchy import Node, build_hierarchy
from app.services.parse.structure.reading_order import reading_order
from app.services.parse.structure.tables import (
    RulingGeometry,
    detect_tables,
    reconstruct_table,
    ruling_geometry,
)


def _page_geometry(page) -> RulingGeometry | None:
    """Build the vector ruling/curve geometry (real table evidence) from a pdfplumber page, so the table
    detector can distinguish a real table (ruling-line grid / regular column grid) from a DIAGRAM (block /
    circuit / pin diagram, packaging artwork) whose labels merely pseudo-align. Best-effort: a reader that
    cannot expose lines/rects/curves degrades the detector to the column-regularity check only."""
    try:
        return ruling_geometry(page.lines or [], page.rects or [], page.curves or [])
    except Exception:  # noqa: BLE001
        return None


def _fold_tables(boxes: list[Box], geometry: RulingGeometry | None = None) -> list[Box]:
    """Detect table regions and replace each region's cells with a single 'table' box whose text is the
    reconstructed HTML — so reading order places the table once and the hierarchy attaches it as content.

    `geometry` carries the page's vector rules + curves; the detector's real-table guard uses it to refuse
    folding a diagram into a garbled <table> (G1/G5). When a candidate is NOT a real table its cells are
    left untouched here, so they flow through XY-Cut++ reading order as ordinary text."""
    regions = detect_tables(boxes, geometry)
    if not regions:
        return boxes
    in_table = {id(b): ri for ri, reg in enumerate(regions) for b in reg}
    kept = [b for b in boxes if id(b) not in in_table]
    for reg in regions:
        html = reconstruct_table(reg)
        if not html:
            kept.extend(reg)
            continue
        x0 = min(b.x0 for b in reg); y0 = min(b.y0 for b in reg)
        x1 = max(b.x1 for b in reg); y1 = max(b.y1 for b in reg)
        kept.append(Box(id=reg[0].id, x0=x0, y0=y0, x1=x1, y1=y1, text=html, label="table"))
    return kept

log = structlog.get_logger("terrane.structure")


def structure_tree(pdf_bytes: bytes, only_pages: set[int] | None = None) -> tuple[Node, dict[int, int]] | None:
    """Build the section tree from a digital PDF. Returns (root, page_of_box_id) or None if no text.

    `only_pages` (1-indexed page numbers) restricts the tree to a subset of pages; None = all pages. The
    per-page router passes the digital pages here so a MIXED PDF's scanned pages are handled separately and
    only the text-layer pages go through the (0-error native-text) structure engine.
    """
    try:
        import pdfplumber
        doc = pdfplumber.open(io.BytesIO(pdf_bytes))
    except Exception as e:  # noqa: BLE001
        log.warning("structure_open_failed", error=str(e))
        return None
    all_boxes: list[Box] = []
    page_of: dict[int, int] = {}
    gid = 0
    try:
        for pno, page in enumerate(doc.pages, start=1):
            if only_pages is not None and pno not in only_pages:
                continue
            ordered = reading_order(_fold_tables(extract_page_boxes(page), _page_geometry(page)))
            for b in ordered:
                b.id = gid
                page_of[gid] = pno
                all_boxes.append(b)
                gid += 1
    finally:
        doc.close()
    if not all_boxes:
        return None
    root = build_hierarchy(all_boxes, page_of=lambda b: page_of.get(b.id))
    return root, page_of


def _emit(node: Node, page_of: dict[int, int], out: list[str], seen_page: list[int]) -> None:
    """Depth-first emit of headings + content as Markdown, inserting page markers on page change."""
    def page_marker(b: Box):
        p = page_of.get(b.id)
        if p is not None and p != seen_page[0]:
            seen_page[0] = p
            out.append(f"\n<!-- Page {p} -->")

    if node.level > 0 and node.title:
        out.append(("#" * min(node.level, 6)) + " " + node.title)
    for b in node.boxes:
        page_marker(b)
        out.append(b.text)
    for c in node.children:
        _emit(c, page_of, out, seen_page)


def structure_markdown(pdf_bytes: bytes) -> str | None:
    """Digital PDF -> structured Markdown (headings + native text + page markers). None if no text layer."""
    if not has_text_layer(pdf_bytes):
        return None
    res = structure_tree(pdf_bytes)
    if res is None:
        return None
    root, page_of = res
    out: list[str] = []
    _emit(root, page_of, out, seen_page=[0])
    md = "\n".join(s for s in out if s is not None).strip()
    log.info("structure_markdown_built", chars=len(md))
    return md or None


def structure_markdown_pages(pdf_bytes: bytes, pages: set[int]) -> str | None:
    """Structure engine on a SUBSET of pages -> structured Markdown (exact native text + page markers).

    Used by the per-page router: only the digital (text-layer) pages of a (possibly mixed) PDF are routed
    here, so their exact native text never gets re-OCR'd. Returns None when the subset has no usable text.
    The emitted Markdown carries `<!-- Page N -->` markers for the pages it covers (N = original page no.),
    so the router can interleave scanned-page output in page order.
    """
    if not pages:
        return None
    res = structure_tree(pdf_bytes, only_pages=pages)
    if res is None:
        return None
    root, page_of = res
    out: list[str] = []
    _emit(root, page_of, out, seen_page=[0])
    md = "\n".join(s for s in out if s is not None).strip()
    return md or None


_PAGE_MARKER = re.compile(r"^<!--\s*Page\s+(\d+)\s*-->\s*$", re.M)


def splice_figures(md: str, figures: dict[int, list[str]]) -> str:
    """Insert each page's figure placeholders IN PLACE in structured Markdown, right after that page's
    `<!-- Page N -->` marker (the page's reading-order start). `figures` = {page_no: [markdown_snippet, ...]}.

    The structure engine emits a `<!-- Page N -->` marker at every page change, so splicing after the marker
    puts the figure at the top of its page's content (the figure's reading-order position on a digital page is
    not recoverable from native text alone, so page-top is the faithful, deterministic placement). Each snippet
    is a self-contained `![caption](ref)` paragraph (blank line around it) so chunking keeps the caption whole
    and never splits it from neighbouring text. Pages with no marker (or no figures) are unchanged."""
    if not figures:
        return md
    placed: set[int] = set()

    def _ins(m) -> str:
        pno = int(m.group(1))
        snippets = figures.get(pno)
        if not snippets or pno in placed:
            return m.group(0)
        placed.add(pno)
        # Trailing blank line is REQUIRED: the structure engine joins a page's text boxes with single newlines,
        # so without a blank line after the last snippet the page's first text line would glue onto the
        # placeholder's paragraph and the `![...]` marker would no longer be its own (atomic) chunk paragraph.
        return m.group(0) + "\n\n" + "\n\n".join(snippets) + "\n"

    out = _PAGE_MARKER.sub(_ins, md)
    # Any figures whose page had no marker (page produced no text) -> append a small per-page block so the
    # figure + caption are never dropped (still searchable + viewable), tagged with their page.
    leftover = [p for p in sorted(figures) if p not in placed and figures[p]]
    if leftover:
        tail = []
        for p in leftover:
            tail.append(f"\n<!-- Page {p} -->\n\n" + "\n\n".join(figures[p]))
        out = out + "\n" + "\n".join(tail)
    return out

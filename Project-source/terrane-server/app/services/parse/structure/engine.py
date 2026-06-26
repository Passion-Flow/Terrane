"""Structure engine orchestrator — PDF bytes -> reading-ordered, hierarchical structured Markdown.

Ties together: native box extraction (per page) -> XY-Cut++ reading order (per page) -> cross-page
font/numbering hierarchy -> Markdown with `#` headings and `<!-- Page N -->` markers. The emitted
Markdown is exact native text (no OCR error) and carries the structure, so the existing tree builder
and chunker stay consistent. Returns None when the PDF has no usable text layer (caller -> VL/OCR).
"""

from __future__ import annotations

import io

import structlog

from app.services.parse.structure.box import Box
from app.services.parse.structure.extract import extract_page_boxes, has_text_layer
from app.services.parse.structure.hierarchy import Node, build_hierarchy
from app.services.parse.structure.reading_order import reading_order
from app.services.parse.structure.tables import detect_tables, reconstruct_table


def _fold_tables(boxes: list[Box]) -> list[Box]:
    """Detect table regions and replace each region's cells with a single 'table' box whose text is the
    reconstructed HTML — so reading order places the table once and the hierarchy attaches it as content."""
    regions = detect_tables(boxes)
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
            ordered = reading_order(_fold_tables(extract_page_boxes(page)))
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

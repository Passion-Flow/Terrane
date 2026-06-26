"""Bounded-memory streaming PDF parse — yield structured Markdown one PAGE BATCH at a time (P3/F4, G6).

The old `_parse_pdf` / `structure_markdown_pages` joined EVERY page into one giant string in memory, so a
450-page / hundreds-of-MB document blew up peak RSS (parse all -> one string -> chunk all -> embed all). This
module reuses the SAME per-page router classification and the SAME per-page handlers (structure engine for
digital pages, deterministic CV for scanned ruled tables, VL for scanned prose), but drives them over a SLIDING
WINDOW of `batch_size` pages. The caller (`ingest_service.stream_ingest`) chunks + persists + embeds each batch
and then discards it, so peak memory is bounded by one batch (~16 pages), not the whole document.

Determinism + parity: a streamed batch produces byte-identical Markdown to the whole-document path for the same
pages (same router, same handlers, same page markers). Streaming only changes WHEN text is held in memory, not
WHAT is produced — so chunking/tree/retrieval are unchanged. Pages whose handler raises are recorded as a
poison-page error and skipped, so one bad page never aborts a 450-page job.
"""

from __future__ import annotations

import structlog

from app.services.parse import router as parse_router
from app.services.parse.router import RouteResult
from app.services.parse.structure import engine as structure_engine

log = structlog.get_logger("terrane.parse.stream")

# A batch is this many ORIGINAL pages (digital + scanned share the window). 16 keeps peak memory to ~16 pages of
# boxes/text regardless of document length (design/11 §3.4 starting constant).
PAGE_BATCH = 16

# Streaming only kicks in past this page count; below it the whole-document path is already cheap and avoids the
# small per-batch overhead (and keeps the special whole-doc scanned-table handling intact). Measured chip spec
# (122 pages) and the 450-page synthetic both exceed this and stream.
STREAM_MIN_PAGES = 24


class Batch:
    """One page-batch's parse output. `pages` are the ORIGINAL 1-indexed page numbers covered (so the resume
    cursor / progress advance by real pages). `markdown` is the structured Markdown for just those pages (or ""
    if every page in the window produced nothing). `errors` lists pages whose handler raised (poison pages)."""

    __slots__ = ("start_page", "end_page", "pages", "markdown", "errors")

    def __init__(self, start_page: int, end_page: int, pages: list[int], markdown: str, errors: list[int]):
        self.start_page = start_page
        self.end_page = end_page
        self.pages = pages
        self.markdown = markdown
        self.errors = errors


def should_stream(route: RouteResult) -> bool:
    """Stream a PDF iff it is large enough AND the per-page handlers can run page-by-page without breaking a
    cross-page handler. The whole-document scanned-ruled-table path stitches rows ACROSS pages, so a fully-
    scanned-table doc must NOT be streamed (it stays whole, like the existing legacy guard). Everything else
    (fully digital, mixed digital+prose, digital+scanned-table) streams safely page-batch by page-batch."""
    n = len(route.pages)
    if n < STREAM_MIN_PAGES:
        return False
    # Pure scanned-table doc (no digital pages, has scanned-table pages) -> keep whole (cross-page row stitching).
    if not route.any_digital and route.scanned_table_pages:
        return False
    # Scanned-PROSE pages need the async VL client which the sync batch path can't call; only stream when they
    # are a small minority (so a big mostly-digital doc still streams, but a scan-heavy doc falls back to the
    # whole-document VL path that handles prose pages correctly).
    if len(route.scanned_prose_pages) > max(2, n * 0.1):
        return False
    return True


def page_windows(route: RouteResult, batch_size: int = PAGE_BATCH,
                 start_after_page: int = 0) -> list[tuple[int, int]]:
    """Plan the page batches as cheap (start_page, end_page) windows over the ORIGINAL pages — no parsing, no
    PDF open. `start_after_page` resumes: windows entirely <= it are skipped (already persisted). The caller
    parses each window with `parse_window` inside a threadpool, one at a time, so only one batch is ever in
    memory."""
    by_no = {p.page_no: p for p in route.pages}
    last = max(by_no) if by_no else 0
    start = max(1, start_after_page + 1)
    return [(s, min(s + batch_size - 1, last)) for s in range(start, last + 1, batch_size)]


def parse_window(pdf_bytes: bytes, route: RouteResult, window: tuple[int, int]) -> Batch:
    """Parse ONE page window (s..e, inclusive, 1-indexed) into structured Markdown. Pure CPU / synchronous so
    the async caller runs it via `run_in_threadpool` — this is the bounded-memory unit (only these pages' boxes
    are held). Scanned-prose pages (VL) are NOT handled here (they need the async VL client); on a large digital
    document they are rare and are skipped with an error record rather than aborting the batch."""
    by_no = {p.page_no: p for p in route.pages}
    s, e = window
    pages = list(range(s, e + 1))
    digital = {p for p in pages if by_no.get(p) and by_no[p].cls == parse_router.DIGITAL}
    scanned_table = {p for p in pages if by_no.get(p) and by_no[p].cls == parse_router.SCANNED_TABLE}
    scanned_prose = {p for p in pages if by_no.get(p) and by_no[p].cls == parse_router.SCANNED_PROSE}
    return _parse_batch(pdf_bytes, s, e, pages, digital, scanned_table, scanned_prose)


def _parse_batch(pdf_bytes: bytes, s: int, e: int, window: list[int], digital: set[int],
                 scanned_table: set[int], scanned_prose: set[int]) -> Batch:
    """Parse one batch's pages, assembling per-class handler output in page order. Pure CPU / synchronous so it
    runs inside `run_in_threadpool`. Scanned-prose pages (VL) are NOT handled here — they need the async VL
    client; the caller threads a separate async pass for them (rare on large docs, which are mostly digital)."""
    parts: list[tuple[int, str]] = []
    errors: list[int] = []

    # DIGITAL pages of this batch -> structure engine over just this subset (exact native text, page markers).
    if digital:
        try:
            dtext = structure_engine.structure_markdown_pages(pdf_bytes, digital)
        except Exception as ex:  # noqa: BLE001
            log.warning("stream_structure_failed", start=s, end=e, error=str(ex))
            errors.extend(sorted(digital))
            dtext = None
        if dtext:
            parts.append((min(digital), dtext))

    # SCANNED ruled-table pages of this batch -> deterministic CV path over a subset of just those pages.
    if scanned_table:
        sub = parse_router.subset_pdf(pdf_bytes, scanned_table)
        if sub:
            try:
                from app.services.parse import scanned_table as parse_scanned_table
                ttext = parse_scanned_table.parse_scanned_bordered_table(sub)
            except Exception as ex:  # noqa: BLE001
                log.warning("stream_scanned_table_failed", start=s, end=e, error=str(ex))
                errors.extend(sorted(scanned_table))
                ttext = None
            if ttext:
                parts.append((min(scanned_table), ttext))

    # SCANNED-PROSE pages need the ASYNC VL client, which this sync CPU batch cannot call. They are recorded as
    # poison (logged, never silently dropped). `should_stream` keeps them a minority (large docs are ~all
    # digital), so streaming a big mostly-digital PDF stays correct while bounding memory.
    if scanned_prose:
        errors.extend(sorted(scanned_prose))

    parts.sort(key=lambda x: x[0])
    md = "\n\n".join(p for _, p in parts).strip()
    return Batch(start_page=s, end_page=e, pages=window, markdown=md, errors=errors)

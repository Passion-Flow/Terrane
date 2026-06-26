"""Figure handling for DIGITAL PDF pages — keep figures as an IMAGE + label-only caption, never as text.
See design/11-allfile-parsing-roadmap.md §3.1 (component F1, fixes G2/G3) and §0.

The roadmap's core judgement: a VLM reads a diagram's node/box LABELS reliably but gets its CONNECTIONS
(edges/arrows/wiring) wrong (flowchart benchmarks: edge F1 < 0.30). So a topology diagram (block / circuit /
pin / signal) — and any figure or product image — must be KEPT AS AN IMAGE crop and described only by its
readable labels, NEVER serialized into "structured connections as text" (which would index hallucinated
wiring). Before P0 the structure engine emitted no `![...]` at all: vector diagrams flowed as loose text and
raster figures on digital pages were dropped; `enhance_pdf` was raster-only (≥6KB), capped, and dumped its
captions at the END of the doc. This module fixes that for the DIGITAL (structure-engine) path:

  1. detect_figure_regions — per page, find figure regions: (a) embedded RASTER image objects (pypdfium2
     page image objects), filtered against header/footer chrome + tiny icons; (b) DENSE VECTOR-GRAPHICS
     clusters (curves/paths the table detector left un-folded as a diagram). Each region -> (page, idx, bbox)
     in reading order (top-to-bottom).
  2. crop the region's page-points bbox to a WebP (pypdfium2 page render, sliced) and store it in object
     storage under storage.figure_key(sid, page, idx) so it is servable exactly like a page image.
  3. VL LABEL-ONLY caption (vl._FIGURE_LABEL_PROMPT) on the crop — short, labels only, no invented edges.
  4. return per-page Markdown `![caption](figure-ref)` so the caller splices each figure in at its page's
     reading-order position (right after the `<!-- Page N -->` marker), so the parsed view shows the crop
     inline and the caption is chunked as searchable text.

Bounded: a configurable cap on VL calls per document; for very large docs the most prominent figures (by
area) are captioned and the count of skipped figures is reported (never silently dropped). Pure-CPU detection;
VL only for the short caption (degrades to a generic placeholder caption when no vl channel is configured).
"""

from __future__ import annotations

import asyncio
import base64
import io
import uuid

import structlog

from app.services import model_client, storage
from app.services.model_channels import get_channel
from app.services.parse import vl as parse_vl

log = structlog.get_logger("terrane.parse.figures")

# --- detection thresholds (calibrated on the real docs: UMS9620 chip spec p11 block diagram = 132 curves +
#     254 rects + small embedded rasters; S63AR packaging p1 = 4353 curves, 0 raster; chip-spec data-table
#     pages 98/105 = 0 curves -> NO figure; the 102x33 header logo repeats on 28 pages -> chrome). -------------
_MIN_FIG_AREA_FRAC = 0.015   # a figure region must cover >= this fraction of the page area (drops tiny icons)
_MAX_FIG_AREA_FRAC = 0.96    # ... and not (near) the WHOLE page (a full-page background scan is not a "figure")
_CHROME_MARGIN_FRAC = 0.10   # an image whose center sits within this top/bottom margin band is header/footer chrome
_CHROME_REPEAT_MIN = 4       # an image whose (bbox,size) signature repeats on >= this many pages = a logo -> drop
_MIN_VECTOR_PRIMS = 24       # a vector cluster needs >= this many curves/rects to count as a diagram region
_MIN_CURVES_IN_CLUSTER = 8   # ... including >= this many CURVES (the diagram tell; a ruled table has ~0 curves)
_GRID_N = 24                 # occupancy-grid resolution (NxN cells over the page) for connected-component clustering

_RENDER_SCALE = 130 / 72.0   # match render_service.DPI so a figure crop is the same resolution as page images
_CROP_PAD = 4.0              # page-points padding around a detected region so labels at the edge aren't clipped
_VL_MAX_EDGE = 1600          # downscale the VL INPUT to <= this on the long edge (stored crop stays full-res):
                             # a full-page artwork crop is multi-MB and times out / is rejected; ~1600px keeps
                             # labels legible while the call is fast + reliable.
_VL_CONCURRENCY = 4
# Per-document VL caption budget. Independent of vl._MAX_CALLS (that caps page-OCR/raster-image enrichment);
# figures get their own budget so a figure-dense spec book is well covered without unbounded cost. Beyond the
# budget the crop is still stored + placed (viewable); only the caption is skipped, and the skipped count is
# reported (never a silent drop).
DEFAULT_MAX_VL_FIGURES = 60


def _bbox_union(bboxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    return (min(b[0] for b in bboxes), min(b[1] for b in bboxes),
            max(b[2] for b in bboxes), max(b[3] for b in bboxes))


def _vector_clusters(prims: list[tuple[float, float, float, float, bool]], page_w: float, page_h: float
                     ) -> list[tuple[float, float, float, float, int, int]]:
    """Group vector primitives (curve/rect bboxes; bool = is_curve) into figure regions via an occupancy-grid
    connected-component (DBSCAN-style density clustering without the dependency).

    A coarse NxN grid is laid over the page; a cell is "occupied" if any primitive's center falls in it. 8-
    connected runs of occupied cells form components — so a block/circuit diagram whose strokes are spread out
    becomes ONE region (its union bbox) instead of being sliced, while two diagrams separated by whitespace stay
    apart. Returns [(x0,y0,x1,y1, n_prims, n_curves)] for components with enough primitives AND enough CURVES
    (the diagram tell: a ruled table has ~0 curves, so it never forms a vector figure here)."""
    if not prims:
        return []
    n = _GRID_N
    cw = page_w / n if page_w > 0 else 1.0
    ch = page_h / n if page_h > 0 else 1.0
    cell_to_prims: dict[tuple[int, int], list[int]] = {}
    for i, p in enumerate(prims):
        cx = (p[0] + p[2]) / 2.0
        cy = (p[1] + p[3]) / 2.0
        gx = min(n - 1, max(0, int(cx / cw)))
        gy = min(n - 1, max(0, int(cy / ch)))
        cell_to_prims.setdefault((gx, gy), []).append(i)

    occupied = set(cell_to_prims.keys())
    seen: set[tuple[int, int]] = set()
    out: list[tuple[float, float, float, float, int, int]] = []
    for start in occupied:
        if start in seen:
            continue
        # flood-fill the 8-connected component of occupied cells
        comp = [start]
        seen.add(start)
        stack = [start]
        while stack:
            gx, gy = stack.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    nb = (gx + dx, gy + dy)
                    if nb in occupied and nb not in seen:
                        seen.add(nb)
                        comp.append(nb)
                        stack.append(nb)
        idxs = [i for cell in comp for i in cell_to_prims[cell]]
        n_curves = sum(1 for i in idxs if prims[i][4])
        if len(idxs) < _MIN_VECTOR_PRIMS or n_curves < _MIN_CURVES_IN_CLUSTER:
            continue
        x0, y0, x1, y1 = _bbox_union([(prims[i][0], prims[i][1], prims[i][2], prims[i][3]) for i in idxs])
        out.append((x0, y0, x1, y1, len(idxs), n_curves))
    return out


def _chrome_signatures(pl, max_pages: int = 40) -> set[tuple[int, int, int, int]]:
    """(x0,top,w,h)-rounded signatures of raster images that REPEAT across pages = header/footer logos/chrome.

    Scanned over the first `max_pages` pages; a signature seen on >= `_CHROME_REPEAT_MIN` pages is chrome and
    its instances are excluded from figure detection (the chip-spec 102x33 logo repeats on 28 pages)."""
    from collections import Counter
    sig: Counter = Counter()
    for p in pl.pages[:max_pages]:
        try:
            images = p.images or []
        except Exception:  # noqa: BLE001
            continue
        seen_on_page: set[tuple[int, int, int, int]] = set()
        for im in images:
            # .get() defaults: one image missing a key must not abort the whole-doc chrome scan (which would
            # let repeated logos leak through as figures on every page).
            s = (round(im.get("x0", 0)), round(im.get("top", 0)),
                 round(im.get("width", 0)), round(im.get("height", 0)))
            if s not in seen_on_page:
                seen_on_page.add(s)
                sig[s] += 1
    return {s for s, c in sig.items() if c >= _CHROME_REPEAT_MIN}


def detect_figure_regions(pdf_bytes: bytes, pages: set[int] | None = None
                          ) -> dict[int, list[tuple[float, float, float, float]]]:
    """Per-page figure regions for the DIGITAL path. Returns {page_no(1-based): [bbox(x0,y0,x1,y1) in page
    points, top-origin] in reading order (top-to-bottom)}.

    A figure region is either (a) an embedded raster image object (filtered: not chrome, not a tiny icon, not
    a full-page background), or (b) a dense vector-graphics cluster (curves/paths the table detector left
    un-folded — a block/circuit/pin diagram or packaging artwork). `pages` (1-based) restricts to a subset
    (the router's digital pages); None = all pages. Pure CPU, deterministic, best-effort (errors -> {})."""
    try:
        import pdfplumber
    except Exception:  # noqa: BLE001
        return {}
    try:
        pl = pdfplumber.open(io.BytesIO(pdf_bytes))
    except Exception:  # noqa: BLE001
        return {}
    result: dict[int, list[tuple[float, float, float, float]]] = {}
    try:
        chrome = _chrome_signatures(pl)
        for pno, page in enumerate(pl.pages, start=1):
            if pages is not None and pno not in pages:
                continue
            pw, ph = float(page.width or 1.0), float(page.height or 1.0)
            page_area = pw * ph
            if page_area <= 0:
                continue
            regions: list[tuple[float, float, float, float]] = []

            # (a) raster image objects
            for im in (page.images or []):
                try:
                    x0, y0, x1, y1 = float(im["x0"]), float(im["top"]), float(im["x1"]), float(im["bottom"])
                except (KeyError, TypeError, ValueError):
                    continue
                if (round(im.get("x0", 0)), round(im.get("top", 0)),
                        round(im.get("width", 0)), round(im.get("height", 0))) in chrome:
                    continue  # repeated logo / footer chrome
                w, h = x1 - x0, y1 - y0
                if w <= 0 or h <= 0:
                    continue
                frac = (w * h) / page_area
                if frac < _MIN_FIG_AREA_FRAC or frac > _MAX_FIG_AREA_FRAC:
                    continue
                cy = (y0 + y1) / 2.0
                if cy < ph * _CHROME_MARGIN_FRAC or cy > ph * (1 - _CHROME_MARGIN_FRAC):
                    if frac < 0.06:   # small AND in the top/bottom margin band -> header/footer mark
                        continue
                regions.append((x0, y0, x1, y1))

            # (b) dense vector-graphics clusters (curves are the diagram tell; a ruled table has ~0 curves)
            prims: list[tuple[float, float, float, float, bool]] = []
            try:
                for c in (page.curves or []):
                    prims.append((float(c["x0"]), float(c["top"]), float(c["x1"]), float(c["bottom"]), True))
                for r in (page.rects or []):
                    prims.append((float(r["x0"]), float(r["top"]), float(r["x1"]), float(r["bottom"]), False))
            except (KeyError, TypeError, ValueError):
                prims = []
            # A single diagram's strokes/boxes often form a few disconnected vector blobs (the gaps hold its
            # text labels). Merge nearby vector clusters into one diagram region so a block diagram is captured
            # whole (one crop, one caption listing all its labels) instead of sliced into fragments.
            vboxes = [(x0, y0, x1, y1) for x0, y0, x1, y1, _n, _nc in _vector_clusters(prims, pw, ph)]
            merged = _merge_near(vboxes, pw * 0.16, ph * 0.16, wide=max(pw, ph) * 0.5)

            def _area_ok(b: tuple[float, float, float, float]) -> bool:
                f = ((b[2] - b[0]) * (b[3] - b[1])) / page_area
                return _MIN_FIG_AREA_FRAC <= f <= _MAX_FIG_AREA_FRAC

            for mb in merged:
                # If a merge produced an over-large region (e.g. two near-page-filling diagrams unioned), don't
                # DROP it — fall back to the constituent un-merged clusters that individually pass the area gate,
                # so the figures are still captured rather than silently lost.
                use = [mb] if _area_ok(mb) else [v for v in vboxes if _overlaps(v, mb, 0.5)]
                for x0, y0, x1, y1 in use:
                    if not _area_ok((x0, y0, x1, y1)):
                        continue
                    # de-dup against a raster region (or an already-kept vector region) covering the same area
                    if any(_overlaps((x0, y0, x1, y1), rb, 0.6) for rb in regions):
                        continue
                    regions.append((x0, y0, x1, y1))

            if regions:
                regions = _merge_overlaps(regions)
                regions.sort(key=lambda b: (round(b[1] / 8.0), b[0]))  # reading order: top->bottom, then left
                result[pno] = regions
    finally:
        pl.close()
    return result


def _overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float], frac: float) -> bool:
    """True if the intersection of a,b covers >= `frac` of the SMALLER box's area."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0:
        return False
    sa = (a[2] - a[0]) * (a[3] - a[1])
    sb = (b[2] - b[0]) * (b[3] - b[1])
    return inter >= frac * min(sa, sb)


def _axis_overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    """Overlap length of two 1-D intervals (0 if disjoint)."""
    return max(0.0, min(a1, b1) - max(a0, b0))


def _should_merge(a: tuple[float, float, float, float], b: tuple[float, float, float, float],
                  tol_x: float, tol_y: float, wide: float) -> bool:
    """Merge two vector blobs into one diagram region when they are clearly parts of the same figure:
      * both axis gaps within the tight tolerance (adjacent stroke-blobs whose labels sit in the gap), OR
      * they substantially OVERLAP on one axis (side-by-side halves of one wide diagram, or stacked rows of
        one tall diagram) AND the gap on the OTHER axis is within the wider bound. Block diagrams split into a
        left + right stroke-blob with the labels in the middle (chip-spec p11) are joined by the second case."""
    gx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    gy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    if gx <= tol_x and gy <= tol_y:
        return True
    oy = _axis_overlap(a[1], a[3], b[1], b[3]) / max(1.0, min(a[3] - a[1], b[3] - b[1]))
    ox = _axis_overlap(a[0], a[2], b[0], b[2]) / max(1.0, min(a[2] - a[0], b[2] - b[0]))
    if oy >= 0.5 and gx <= wide:   # side-by-side, joined horizontally
        return True
    if ox >= 0.5 and gy <= wide:   # stacked, joined vertically
        return True
    return False


def _merge_near(boxes: list[tuple[float, float, float, float]], tol_x: float, tol_y: float, wide: float
                ) -> list[tuple[float, float, float, float]]:
    """Union vector blobs that belong to the same diagram (see `_should_merge`). Iterates to a fixed point.
    Two genuinely separate, widely-spaced diagrams stay apart."""
    boxes = list(boxes)
    merged = True
    while merged:
        merged = False
        out: list[tuple[float, float, float, float]] = []
        for b in boxes:
            for i, o in enumerate(out):
                if _should_merge(b, o, tol_x, tol_y, wide):
                    out[i] = _bbox_union([o, b])
                    merged = True
                    break
            else:
                out.append(b)
        boxes = out
    return boxes


def _merge_overlaps(boxes: list[tuple[float, float, float, float]]
                    ) -> list[tuple[float, float, float, float]]:
    """Union overlapping figure regions so a raster sub-image inside a vector diagram doesn't double-emit."""
    boxes = list(boxes)
    merged = True
    while merged:
        merged = False
        out: list[tuple[float, float, float, float]] = []
        for b in boxes:
            for i, o in enumerate(out):
                if _overlaps(b, o, 0.35):
                    out[i] = _bbox_union([o, b])
                    merged = True
                    break
            else:
                out.append(b)
        boxes = out
    return boxes


def _crop_pages(pdf_bytes: bytes, regions_by_page: dict[int, list[tuple[float, float, float, float]]]
                ) -> dict[tuple[int, int], bytes]:
    """Render each needed page once and slice every region's bbox to a WebP. Returns {(page,idx): webp bytes}.

    pypdfium2 renders top-origin (same y convention as pdfplumber bboxes), at the page-image DPI so a figure
    crop matches the served page resolution. Best-effort per region (a failed crop is skipped)."""
    try:
        import pypdfium2 as pdfium
    except Exception:  # noqa: BLE001
        return {}
    try:
        doc = pdfium.PdfDocument(pdf_bytes)
    except Exception:  # noqa: BLE001
        return {}
    crops: dict[tuple[int, int], bytes] = {}
    try:
        npages = len(doc)
        for pno, regions in regions_by_page.items():
            if pno - 1 >= npages:
                continue
            page = doc[pno - 1]
            try:
                pil = page.render(scale=_RENDER_SCALE).to_pil()
            except Exception:  # noqa: BLE001
                page.close()
                continue
            page.close()
            W, H = pil.size
            for idx, (x0, y0, x1, y1) in enumerate(regions):
                left = max(0, int((x0 - _CROP_PAD) * _RENDER_SCALE))
                top = max(0, int((y0 - _CROP_PAD) * _RENDER_SCALE))
                right = min(W, int((x1 + _CROP_PAD) * _RENDER_SCALE))
                bottom = min(H, int((y1 + _CROP_PAD) * _RENDER_SCALE))
                if right - left < 8 or bottom - top < 8:
                    continue
                try:
                    crop = pil.crop((left, top, right, bottom))
                    buf = io.BytesIO()
                    crop.convert("RGB").save(buf, format="WEBP", quality=80, method=4)
                    crops[(pno, idx)] = buf.getvalue()
                except Exception:  # noqa: BLE001
                    continue
    finally:
        doc.close()
    return crops


def _vl_b64(webp: bytes) -> str | None:
    """Base64 of a downscaled JPEG copy of the crop for the VL call (the stored crop stays full-res WebP).
    Long edge <= `_VL_MAX_EDGE` so a multi-MB full-page artwork crop becomes a small, fast, reliable request.
    Returns None if re-encoding fails (the caller then skips captioning rather than sending bytes whose real
    format would not match the `image/jpeg` data-URL the VL client declares)."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(webp))
        if max(im.size) > _VL_MAX_EDGE:
            im.thumbnail((_VL_MAX_EDGE, _VL_MAX_EDGE))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa: BLE001
        return None


_MAX_CAPTION_CHARS = 360   # keep a caption short enough that placeholder + `![](ref)` overhead + a deep
                           # breadcrumb prefix still fit ONE chunk (chunk budget = 500 - len(breadcrumb))


def _placeholder(caption: str, ref: str) -> str:
    """One Markdown image placeholder + caption. `![caption](ref)` keeps the caption on the image's own
    paragraph; the caller splices a blank line around it so chunking treats it as one atomic block (never
    splitting a caption from its image). The caption is collapsed to one line and bounded in length so it
    always fits a single chunk (a very long label list is truncated with an ellipsis — short by design)."""
    cap = " ".join((caption or "").split())  # collapse whitespace/newlines -> one chunkable line
    if len(cap) > _MAX_CAPTION_CHARS:
        cap = cap[:_MAX_CAPTION_CHARS].rstrip() + "…"
    cap = cap.replace("]", "［").replace("[", "［")  # keep the Markdown image syntax unambiguous
    return f"![{cap}]({ref})"


async def enrich_figures(db, pdf_bytes: bytes, raw_source_id: uuid.UUID | str | None,
                         pages: set[int] | None = None, *,
                         max_vl: int = DEFAULT_MAX_VL_FIGURES) -> dict[int, list[str]]:
    """Detect figures on digital pages, crop+store each, VL-caption (label-only), and return per-page Markdown
    placeholders for IN-PLACE insertion. Returns {page_no: [markdown_snippet, ...]} (reading order per page).

    `raw_source_id` (= the source's id, used in `storage.figure_key`) makes crops servable like page images;
    when None (e.g. the in-memory eval that has no DB row) crops are not stored and figures are skipped (no
    servable ref, no cost). VL captioning is bounded by `max_vl`; beyond it the crop is still stored + placed
    (viewable) but gets a neutral caption, and the skipped-caption count is logged (never a silent drop)."""
    if raw_source_id is None:
        return {}  # no servable target -> don't fabricate refs (keeps the no-DB eval path a pure no-op)
    try:
        regions_by_page = await asyncio.to_thread(detect_figure_regions, pdf_bytes, pages)
    except Exception as e:  # noqa: BLE001
        log.warning("figure_detect_failed", error=str(e))
        return {}
    if not regions_by_page:
        return {}
    total = sum(len(v) for v in regions_by_page.values())

    crops = await asyncio.to_thread(_crop_pages, pdf_bytes, regions_by_page)
    if not crops:
        return {}

    # Store every crop so the figure is viewable via the figure-serving endpoint. A failed upload does NOT drop
    # the figure: its placeholder + caption are still emitted (the caption is the searchable content; the crop
    # ref simply 404s until storage recovers) — "never silently drop".
    try:
        await storage.ensure_bucket()
    except Exception:  # noqa: BLE001
        pass
    n_stored = 0
    for (pno, idx), webp in crops.items():
        try:
            await storage.get_adapter().upload(storage.figure_key(raw_source_id, pno, idx), webp,
                                               content_type="image/webp")
            n_stored += 1
        except Exception as e:  # noqa: BLE001
            log.warning("figure_store_failed", page=pno, idx=idx, error=str(e))

    # VL label-only captions, most-prominent-first (by crop area), bounded by max_vl. No vl channel -> every
    # crop is still placed with a neutral caption (viewable, no cost). Beyond the budget the figure is still
    # placed + viewable; only its caption is skipped, and the skipped count is reported. The vl channel is
    # resolved ONCE here and threaded into each call: the captions run concurrently over the SAME ingest
    # session, and a per-call `get_channel(db)` query on a shared AsyncSession is not safe.
    channel = await get_channel(db, "vl")
    have_vl = channel is not None
    # Rank by figure AREA (page-points bbox) so the budget captions the most prominent figures first — a
    # block/circuit diagram, not whichever crop happens to compress to the most bytes.
    area = {(pno, idx): (b[2] - b[0]) * (b[3] - b[1])
            for pno, regs in regions_by_page.items() for idx, b in enumerate(regs)}
    keys = sorted(crops.keys(), key=lambda k: -area.get(k, 0.0))
    to_caption = keys[:max_vl] if have_vl else []
    skipped_caption = (len(keys) - len(to_caption)) if have_vl else 0

    sem = asyncio.Semaphore(_VL_CONCURRENCY)
    captions: dict[tuple[int, int], str] = {}

    async def _cap(key: tuple[int, int]) -> None:
        b64 = await asyncio.to_thread(_vl_b64, crops[key])
        if b64 is None:
            return
        async with sem:
            try:
                txt = await model_client.vl_caption(db, b64, prompt=parse_vl._FIGURE_LABEL_PROMPT,
                                                    channel=channel)
            except Exception:  # noqa: BLE001
                txt = None
        if txt and txt.strip():
            captions[key] = parse_vl._strip_fence(txt).strip()

    if to_caption:
        await asyncio.gather(*[_cap(k) for k in to_caption])

    out: dict[int, list[str]] = {}
    n_captioned = 0
    for (pno, idx) in sorted(crops.keys()):
        ref = f"figure/{pno}/{idx}"   # resolved by the figure-serving endpoint (parallels the page-image route)
        cap = captions.get((pno, idx))
        if cap:
            n_captioned += 1
        else:
            cap = f"图（第{pno}页）"   # neutral placeholder caption when uncaptioned (still viewable + located)
        out.setdefault(pno, []).append(_placeholder(cap, ref))

    log.info("figures_enriched", source=str(raw_source_id), detected=total, cropped=len(crops),
             stored=n_stored, captioned=n_captioned, caption_skipped=skipped_caption, vl=have_vl)
    return out

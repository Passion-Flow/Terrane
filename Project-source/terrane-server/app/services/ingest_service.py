"""Knowledge base ingestion + hybrid retrieval (platform database terrane_main).

Ingestion: text source -> chunking -> persist -> call the embedding channel to backfill chunks.embedding (halfvec, raw SQL ::halfvec).
Retrieval: dual recall via vector (HNSW cosine) + lexical (pg_trgm) -> merge -> rerank (qwen3-rerank) for fine ranking.
Graceful degradation throughout: no embed channel -> lexical only; no rerank -> merge vector/lexical scores.
"""

from __future__ import annotations

import hashlib
import re
import uuid

import structlog
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb_content import Chunk, RawSource
from app.services import model_client
from app.services.model_client import ModelError

log = structlog.get_logger("terrane.ingest")

_CHUNK_CHARS = 500
_OVERLAP = 60
_RECALL = 20  # Per-path recall cap


def content_sha(s: str) -> str:
    """Stable hash of a chunk's content for incremental dedup. Normalises only trailing/leading whitespace so a
    cosmetically-unchanged chunk hashes identically across reingests and is NOT re-embedded."""
    return hashlib.sha256(s.strip().encode("utf-8")).hexdigest()


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")

# A figure placeholder paragraph `![caption](ref)` (the parser's in-place figure marker). It is ATOMIC during
# chunking: the caption text must never be window-split away from its image ref (that would break the markdown
# AND detach a figure's searchable caption from the figure). Matches a paragraph that is a single image marker.
_FIG_PLACEHOLDER = re.compile(r"^!\[[^\]]*\]\([^)]*\)$")

# A self-contained HTML table; [\s\S] so the rows may span newlines. Greedy is fine — one table per match here.
_HTML_TABLE = re.compile(r"<table\b[^>]*>[\s\S]*?</table>", re.I)
_MD_PIPE_ROW = re.compile(r"^\s*\|.*\|\s*$")            # a markdown pipe-table row line: | a | b |
_MD_PIPE_SEP = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")    # the |---|:--:|---| separator row (only -, :, |, space)


def _is_table_block(p: str) -> bool:
    """True if a paragraph is (or contains) a table that must stay structurally intact during chunking."""
    s = p.strip()
    if _HTML_TABLE.search(s):
        return True
    lines = [ln for ln in s.splitlines() if ln.strip()]
    return len(lines) >= 2 and all(_MD_PIPE_ROW.match(ln) for ln in lines)


def _split_html_table(table_html: str, budget: int) -> list[str]:
    """Split one ``<table>…</table>`` into chunks that are EACH a valid, self-describing table fragment.

    A table is atomic: it is never cut mid-tag. Rule:
      • whole table fits the budget -> one chunk;
      • otherwise pack consecutive ``</tr>`` rows into ``<table>…</table>`` fragments, repeating the
        ``<table>`` open + every header row (``<tr>`` containing ``<th>``, else the first ``<tr>``) on each
        fragment so each chunk parses standalone;
      • a single row larger than the budget is emitted as its own (oversized) fragment — we still never split
        inside a tag, so the fragment stays valid HTML (honest limit: one chunk may exceed ``size``)."""
    m = re.match(r"\s*(<table\b[^>]*>)([\s\S]*?)(</table>)\s*$", table_html, re.I)
    if not m:
        return [table_html]
    open_tag, inner, close_tag = m.group(1), m.group(2), m.group(3)
    rows = re.findall(r"<tr\b[^>]*>[\s\S]*?</tr>", inner, re.I)
    if not rows or len("".join((open_tag, inner, close_tag))) <= budget:
        return [open_tag + inner + close_tag]
    # Header rows repeated on every fragment: all leading rows that carry <th>, else the first row.
    header_rows: list[str] = [r for r in rows if re.search(r"<th\b", r, re.I)]
    if not header_rows:
        header_rows = rows[:1]
    body_rows = rows[len(header_rows):] if header_rows == rows[:len(header_rows)] else rows
    head = open_tag + "".join(header_rows)
    base_len = len(head) + len(close_tag)
    out: list[str] = []
    cur: list[str] = []

    def flush():
        if cur:
            out.append(head + "".join(cur) + close_tag)
            cur.clear()

    for r in body_rows:
        if cur and base_len + sum(len(x) for x in cur) + len(r) > budget:
            flush()
        cur.append(r)
        if base_len + len(r) > budget:   # single row alone already over budget -> emit it on its own
            flush()
    flush()
    return out or [open_tag + inner + close_tag]


def _split_md_table(table_md: str, budget: int) -> list[str]:
    """Split a Markdown pipe-table at row (`|`-line) boundaries, repeating the header + separator row on each
    fragment so every chunk is a valid, self-describing pipe-table. A single row over budget is emitted alone."""
    lines = [ln for ln in table_md.splitlines() if ln.strip()]
    if len(lines) <= 2 or len("\n".join(lines)) <= budget:
        return ["\n".join(lines)]
    header = [lines[0]]
    body_start = 1
    if len(lines) > 1 and _MD_PIPE_SEP.match(lines[1]):
        header.append(lines[1])
        body_start = 2
    head = "\n".join(header)
    base_len = len(head) + 1
    out: list[str] = []
    cur: list[str] = []

    def flush():
        if cur:
            out.append(head + "\n" + "\n".join(cur))
            cur.clear()

    for ln in lines[body_start:]:
        if cur and base_len + sum(len(x) + 1 for x in cur) + len(ln) > budget:
            flush()
        cur.append(ln)
        if base_len + len(ln) + 1 > budget:
            flush()
    flush()
    return out or ["\n".join(lines)]


def _split_table_block(p: str, budget: int) -> list[str]:
    """Split an oversized table paragraph atomically (never mid-tag). HTML and Markdown pipe-tables both keep
    their header context on every fragment so each emitted chunk is a self-describing, parseable table."""
    s = p.strip()
    if _HTML_TABLE.search(s):
        return _split_html_table(s, budget)
    return _split_md_table(s, budget)


def chunk_text(body: str, size: int = _CHUNK_CHARS) -> list[str]:
    """Aggregate paragraphs into ~size-char chunks (light overlap). Heading-aware: a chunk never crosses a
    Markdown heading boundary, so each chunk falls within one section — clean chunk→tree-node attribution.
    Breadcrumb injection: each chunk is prefixed with its section path (`[A › B › C]`), which lifts both
    dense and lexical retrieval by giving every chunk its document context (self-developed enrichment)."""
    # Split at Markdown headings first (keeps the heading at the start of its segment).
    segments = [s for s in re.split(r"(?=^#{1,6}\s)", body, flags=re.M) if s.strip()]
    if not segments:
        segments = [body]
    chunks: list[str] = []
    path: list[tuple[int, str]] = []   # running heading stack -> breadcrumb
    for seg in segments:
        first = seg.lstrip().split("\n", 1)[0]
        m = _HEADING.match(first)
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, title))
        crumb = " › ".join(t for _, t in path)
        prefix = f"[{crumb}]\n" if crumb else ""
        budget = size - len(prefix)
        paras = [p.strip() for p in re.split(r"\n\s*\n", seg) if p.strip()]
        buf = ""

        def flush(b: str):
            if b:
                chunks.append(prefix + b)

        for p in paras:
            if _FIG_PLACEHOLDER.match(p.strip()):
                # A figure placeholder is ATOMIC: keep it whole and never window-split it (that would break the
                # `![caption](ref)` markdown and detach the figure's searchable caption). Attach it to the
                # current buffer if it fits (keeps the figure with its nearby context), else emit it alone.
                if len(buf) + len(p) + 1 <= budget:
                    buf = f"{buf}\n{p}" if buf else p
                else:
                    flush(buf)
                    buf = p if len(p) <= budget else ""
                    if not buf:
                        chunks.append(prefix + p)   # caption alone already > budget -> one (oversized) chunk
            elif len(buf) + len(p) + 1 <= budget:
                buf = f"{buf}\n{p}" if buf else p
            elif _is_table_block(p):
                # A table is ATOMIC: never merge it with prose (would risk a mid-tag cut) and never window-split
                # it. Flush prose, then emit the table as one whole chunk, or as row-boundary fragments that each
                # repeat the header context, so every table chunk is valid, self-describing HTML/markdown.
                flush(buf)
                buf = ""
                for frag in _split_table_block(p, budget):
                    chunks.append(prefix + frag)
            else:
                flush(buf)
                if len(p) > budget:
                    for i in range(0, len(p), max(64, budget - _OVERLAP)):
                        chunks.append(prefix + p[i:i + budget])
                    buf = ""
                else:
                    buf = p
        flush(buf)
    return chunks or ([body.strip()] if body.strip() else [])


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


async def _embed_chunks(db: AsyncSession, chunk_ids: list[uuid.UUID], contents: list[str]) -> int:
    """Call the embedding channel to backfill vectors for chunks. No channel -> 0; failure -> logged but does
    not block ingestion (chunks remain lexically searchable).

    Bulk write (G7): the embeddings come back as one batched call, and the vectors are written with a single
    multi-row `UPDATE ... FROM (VALUES ...)` instead of one round-trip per chunk — at 10k chunks that is one
    statement per batch rather than 10k single-row UPDATEs."""
    if not contents:
        return 0
    try:
        vecs = await model_client.embed_texts(db, contents)
    except ModelError as e:
        log.warning("embed_failed", error=str(e))
        return 0
    if not vecs:
        return 0
    pairs = list(zip(chunk_ids, vecs))
    # Multi-row bulk UPDATE via a VALUES list. Cast id->uuid and the literal->halfvec inside the SET so one
    # statement vectorises the whole batch.
    for i in range(0, len(pairs), 500):  # cap params per statement (each row = 2 binds)
        sub = pairs[i:i + 500]
        rows = ", ".join(f"(:id{j}, :v{j})" for j in range(len(sub)))
        params: dict = {}
        for j, (cid, vec) in enumerate(sub):
            params[f"id{j}"] = str(cid)
            params[f"v{j}"] = _vec_literal(vec)
        await db.execute(text(
            f"UPDATE chunks AS c SET embedding = (d.v)::halfvec "
            f"FROM (VALUES {rows}) AS d(id, v) WHERE c.id = (d.id)::uuid"), params)
    return len(pairs)


async def add_text_source(db: AsyncSession, *, kb_id: uuid.UUID, workspace_id: uuid.UUID,
                          title: str, body: str, kind: str = "text") -> tuple[RawSource, int]:
    """Add a text source -> persist chunks -> backfill vectors. Returns (raw_source, chunk_count)."""
    raw = RawSource(kb_id=kb_id, workspace_id=workspace_id, kind=kind, title=title,
                    mime="text/plain", size_bytes=len(body.encode("utf-8")),
                    status="parsed", parsed_text=body)
    db.add(raw)
    await db.flush()
    pieces = chunk_text(body)
    objs = [Chunk(kb_id=kb_id, raw_source_id=raw.id, ord=i, content=p, token_count=max(1, len(p) // 4),
                  content_sha=content_sha(p))
            for i, p in enumerate(pieces)]
    db.add_all(objs)
    await db.flush()
    embedded = await _embed_chunks(db, [c.id for c in objs], pieces)
    await db.commit()
    await db.refresh(raw)
    await _build_tree_safe(db, raw)
    log.info("text_source_ingested", kb_id=str(kb_id), raw_id=str(raw.id), chunks=len(pieces), embedded=embedded)
    return raw, len(pieces)


async def _build_tree_safe(db: AsyncSession, raw: RawSource) -> None:
    """Build the Retrieval 2.0 structural tree for a source (best-effort; isolated import to avoid cycles)."""
    try:
        from app.services import tree_service
        await tree_service.build_tree(db, raw)
    except Exception as e:  # noqa: BLE001
        log.warning("build_tree_skipped", raw_id=str(raw.id), error=str(e))


async def create_pending_source(db: AsyncSession, *, kb_id: uuid.UUID, workspace_id: uuid.UUID,
                                title: str, mime: str, size: int, status: str = "parsing") -> RawSource:
    """Create a placeholder file source in the "parsing" state (async ingestion: return immediately on upload, parse in the background)."""
    raw = RawSource(kb_id=kb_id, workspace_id=workspace_id, kind="file", title=title,
                    mime=mime or "application/octet-stream", size_bytes=size, status=status)
    db.add(raw)
    await db.flush()
    await db.commit()
    await db.refresh(raw)
    return raw


async def reingest(db: AsyncSession, raw: RawSource, body: str) -> int:
    """Write parsed text to an existing source -> re-chunk -> persist + backfill vectors -> status=parsed.

    INCREMENTAL DEDUP (G6): instead of deleting ALL chunks and re-embedding everything, the new chunks are
    diffed against the existing ones by content hash. A chunk whose content_sha is unchanged AND already has a
    vector is REUSED verbatim (no re-embed); only genuinely new/changed content is embedded. Editing one page of
    a 450-page doc therefore re-embeds a handful of chunks, not ten thousand. Returns the chunk count.
    """
    raw.parsed_text = body
    raw.status = "parsed"
    raw.error = None
    await db.flush()
    pieces = chunk_text(body)
    new_shas = [content_sha(p) for p in pieces]

    # Existing chunks of this source, by content hash -> their embedding presence. A sha that survives AND was
    # embedded can be reused; we keep ONE existing row per surviving sha (the rest are reordered/dropped).
    existing = (await db.execute(text(
        "SELECT id, content_sha, (embedding IS NOT NULL) AS has_emb FROM chunks WHERE raw_source_id = :s"),
        {"s": str(raw.id)})).mappings().all()
    reusable: dict[str, list[str]] = {}      # sha -> [chunk_id, ...] that are embedded and can be kept
    for r in existing:
        if r["content_sha"] and r["has_emb"]:
            reusable.setdefault(r["content_sha"], []).append(str(r["id"]))

    # Snapshot each surviving sha's vector BEFORE deleting (so it can be re-stamped onto the new rows without a
    # re-embed). Rows are re-inserted (ord may shift), then unchanged content carries its old vector forward and
    # only new/changed content is embedded.
    keep_vec: dict[str, str] = {}  # sha -> halfvec text, for shas we can carry forward
    surviving = [s for s in set(new_shas) if s in reusable]
    if surviving:
        vrows = (await db.execute(text(
            "SELECT content_sha, embedding::text AS emb FROM chunks "
            "WHERE raw_source_id = :s AND content_sha = ANY(:shas) AND embedding IS NOT NULL"),
            {"s": str(raw.id), "shas": surviving})).mappings().all()
        for vr in vrows:
            if vr["content_sha"] not in keep_vec and vr["emb"]:
                keep_vec[vr["content_sha"]] = vr["emb"]

    await db.execute(delete(Chunk).where(Chunk.raw_source_id == raw.id))
    objs = [Chunk(kb_id=raw.kb_id, raw_source_id=raw.id, ord=i, content=p, token_count=max(1, len(p) // 4),
                  content_sha=sha)
            for i, (p, sha) in enumerate(zip(pieces, new_shas))]
    db.add_all(objs)
    await db.flush()

    # Carry forward vectors for unchanged content (no re-embed); embed only the rest.
    to_embed_ids: list[uuid.UUID] = []
    to_embed_txt: list[str] = []
    carried = 0
    for c, p, sha in zip(objs, pieces, new_shas):
        if sha in keep_vec:
            await db.execute(text("UPDATE chunks SET embedding = (:v)::halfvec WHERE id = :id"),
                             {"v": keep_vec[sha], "id": str(c.id)})
            carried += 1
        else:
            to_embed_ids.append(c.id)
            to_embed_txt.append(p)
    embedded = await _embed_chunks(db, to_embed_ids, to_embed_txt)
    await db.commit()
    await _build_tree_safe(db, raw)
    log.info("source_reingested", raw_id=str(raw.id), chunks=len(pieces),
             reembedded=embedded, carried=carried)
    return len(pieces)


# ---- Bounded-memory streaming ingest (P3/F4) ----

async def _persist_batch_chunks(db: AsyncSession, *, kb_id: uuid.UUID, raw_id: uuid.UUID,
                                pieces: list[str], ord_offset: int) -> int:
    """Persist one batch's chunks (ord continues from `ord_offset`) + embed them, in a single committed
    transaction so the batch is durable before the next batch is parsed. Returns the number of chunks written.
    A flushed-and-committed batch is the resume unit: a crash after this leaves the batch's chunks on disk and
    the job's `pages_done` is advanced by the caller in the same commit window."""
    if not pieces:
        return 0
    objs = [Chunk(kb_id=kb_id, raw_source_id=raw_id, ord=ord_offset + i, content=p,
                  token_count=max(1, len(p) // 4), content_sha=content_sha(p))
            for i, p in enumerate(pieces)]
    db.add_all(objs)
    await db.flush()
    await _embed_chunks(db, [c.id for c in objs], pieces)
    return len(objs)


async def stream_ingest(db: AsyncSession, *, raw: RawSource, job_id: uuid.UUID, pdf_bytes: bytes,
                        route, file_sha: str, batch_size: int, enrich_batch=None) -> tuple[int, str]:
    """Stream a large PDF into chunks PAGE-BATCH by PAGE-BATCH with a durable checkpoint (G6).

    For each batch of `batch_size` pages: parse just that batch (bounded memory) -> chunk it -> persist +
    embed it -> advance the job's `pages_done` cursor and append the batch text -> COMMIT. Peak memory tracks
    one batch, not the whole document. On resume (`raw`'s job already has pages_done > 0) the already-completed
    pages are skipped: their chunks stay on disk and are NOT re-parsed or re-embedded.

    `enrich_batch(markdown, pages)` (optional, async) enriches ONE batch's Markdown before it is chunked — used
    to splice in-place figure crops + label-only captions (P2) for just this batch's pages, so the P2 figure
    feature is preserved on large docs while memory stays bounded to one batch of figures.

    Returns (total_chunks_written_this_run, assembled_markdown). The assembled Markdown is the concatenation of
    every batch (including any already-persisted text the resume reads back), used only for the tree build /
    parsed_text projection at the end — it is built incrementally, never by holding all pages mid-parse.
    """
    from fastapi.concurrency import run_in_threadpool

    from app.services.parse import stream as parse_stream

    # Resume cursor + running ord come from the durable job row. On a fresh job both are 0.
    job = (await db.execute(text(
        "SELECT pages_done, total_pages FROM ingest_jobs WHERE id = :id"), {"id": str(job_id)})).mappings().one()
    done_pages = int(job["pages_done"] or 0)
    total_pages = int(job["total_pages"] or len(route.pages))

    # On resume, the chunks already on disk define the next ord and the already-parsed text. Read the prefix back
    # (ordered) so the final tree/parsed_text projection is whole, without re-parsing completed pages.
    prior = (await db.execute(text(
        "SELECT content FROM chunks WHERE raw_source_id = :s ORDER BY ord"), {"s": str(raw.id)})).scalars().all()
    ord_offset = len(prior)
    md_parts: list[str] = list(prior)

    written = 0
    poison: list[int] = []
    windows = parse_stream.page_windows(route, batch_size=batch_size, start_after_page=done_pages)
    for window in windows:
        # Parse just this window off the event loop; only one batch's boxes/text are in memory at a time.
        batch = await run_in_threadpool(parse_stream.parse_window, pdf_bytes, route, window)
        if batch.errors:
            poison.extend(batch.errors)
        if batch.markdown:
            md = batch.markdown
            if enrich_batch is not None:
                try:
                    md = await enrich_batch(md, set(batch.pages))
                except Exception as e:  # noqa: BLE001 -- figures are an enrichment, never a parse blocker
                    log.warning("stream_enrich_failed", start=batch.start_page, end=batch.end_page, error=str(e))
            pieces = chunk_text(md)
            n = await _persist_batch_chunks(db, kb_id=raw.kb_id, raw_id=raw.id,
                                            pieces=pieces, ord_offset=ord_offset)
            ord_offset += n
            written += n
            md_parts.append(md)
        # Advance the durable checkpoint: pages_done = last page of this batch, progress %, heartbeat.
        progress = int(batch.end_page / max(1, total_pages) * 100)
        await db.execute(text(
            "UPDATE ingest_jobs SET pages_done = :pd, progress = :pg, status = 'running', "
            "heartbeat_at = now(), updated_at = now() WHERE id = :id"),
            {"pd": batch.end_page, "pg": min(progress, 99), "id": str(job_id)})
        await db.commit()

    assembled = "\n\n".join(p for p in md_parts if p and p.strip()).strip()
    if poison:
        log.warning("stream_poison_pages", raw_id=str(raw.id), pages=poison[:50], count=len(poison))
    log.info("stream_ingest_done", raw_id=str(raw.id), chunks_this_run=written,
             total_pages=total_pages, poison=len(poison))
    return written, assembled


def _src_clause(source_ids: list[uuid.UUID] | None) -> tuple[str, dict]:
    """Build an optional 'limit to these documents' SQL clause for recall (cross-doc routing)."""
    if source_ids:
        return " AND c.raw_source_id = ANY(:srcs)", {"srcs": [str(s) for s in source_ids]}
    return "", {}


async def recall_lexical(db: AsyncSession, *, kb_id: uuid.UUID, query: str, limit: int = _RECALL,
                         source_ids: list[uuid.UUID] | None = None) -> list[dict]:
    """Lexical recall (pg_trgm), ranked. Used by both Fast path and the Deep RRF fusion (R2)."""
    q = query.strip()
    if not q:
        return []
    clause, extra = _src_clause(source_ids)
    rows = (await db.execute(text(f"""
        SELECT c.id, c.content, c.ord, r.title AS src, r.id AS sid, similarity(c.content, :q) AS sc
        FROM chunks c JOIN raw_sources r ON r.id = c.raw_source_id
        WHERE c.kb_id = :kb AND (c.content ILIKE :like OR similarity(c.content, :q) > 0.05){clause}
        ORDER BY sc DESC LIMIT :n
    """), {"kb": str(kb_id), "q": q, "like": f"%{q}%", "n": limit, **extra})).mappings().all()
    return [{"chunk_id": str(r["id"]), "content": r["content"], "ord": r["ord"],
             "source_title": r["src"], "source_id": str(r["sid"]), "score": float(r["sc"] or 0)} for r in rows]


async def recall_by_vector(db: AsyncSession, *, kb_id: uuid.UUID, vec: list[float], limit: int = _RECALL,
                           source_ids: list[uuid.UUID] | None = None, want_embedding: bool = False) -> list[dict]:
    """Vector recall given an explicit query vector (HNSW cosine). want_embedding -> include each chunk's
    stored vector (used by Rocchio pseudo-relevance feedback)."""
    clause, extra = _src_clause(source_ids)
    emb_col = ", c.embedding::text AS emb" if want_embedding else ""
    rows = (await db.execute(text(f"""
        SELECT c.id, c.content, c.ord, r.title AS src, r.id AS sid,
               1 - (c.embedding <=> (:v)::halfvec) AS sc{emb_col}
        FROM chunks c JOIN raw_sources r ON r.id = c.raw_source_id
        WHERE c.kb_id = :kb AND c.embedding IS NOT NULL{clause}
        ORDER BY c.embedding <=> (:v)::halfvec LIMIT :n
    """), {"kb": str(kb_id), "v": _vec_literal(vec), "n": limit, **extra})).mappings().all()
    out = []
    for r in rows:
        d = {"chunk_id": str(r["id"]), "content": r["content"], "ord": r["ord"],
             "source_title": r["src"], "source_id": str(r["sid"]), "score": float(r["sc"] or 0)}
        if want_embedding and r.get("emb"):
            d["_emb"] = r["emb"]
        out.append(d)
    return out


async def recall_vector(db: AsyncSession, *, kb_id: uuid.UUID, query: str, limit: int = _RECALL,
                        source_ids: list[uuid.UUID] | None = None, embed_model: str | None = None) -> list[dict]:
    """Vector recall (HNSW cosine), ranked. Empty if there is no embed channel. (R1)"""
    q = query.strip()
    if not q:
        return []
    try:
        qvec = await model_client.embed_query(db, q, model=embed_model)
    except ModelError as e:
        log.warning("query_embed_failed", error=str(e))
        return []
    if not qvec:
        return []
    return await recall_by_vector(db, kb_id=kb_id, vec=qvec, limit=limit, source_ids=source_ids)


async def search_chunks(db: AsyncSession, *, kb_id: uuid.UUID, query: str, limit: int = 10,
                        embed_model: str | None = None, rerank_model: str | None = None,
                        raw_source_id: uuid.UUID | None = None) -> list[dict]:
    """Hybrid retrieval: vector + lexical recall -> rerank for fine ranking (both degrade gracefully).
    If raw_source_id is given -> limit to that document's chunks (document-level Q&A)."""
    q = query.strip()
    if not q:
        return []
    sid = str(raw_source_id) if raw_source_id else None

    cand: dict[str, dict] = {}

    # Lexical recall (pg_trgm, works for both Chinese and English); when sid is set, limit to that document
    lex = (await db.execute(text("""
        SELECT c.id, c.content, c.ord, r.title AS src, r.id AS sid, similarity(c.content, :q) AS sc
        FROM chunks c JOIN raw_sources r ON r.id = c.raw_source_id
        WHERE c.kb_id = :kb AND (c.content ILIKE :like OR similarity(c.content, :q) > 0.05)
          AND ((:sid)::uuid IS NULL OR c.raw_source_id = (:sid)::uuid)
        ORDER BY sc DESC LIMIT :n
    """), {"kb": str(kb_id), "q": q, "like": f"%{q}%", "n": _RECALL, "sid": sid})).mappings().all()
    for r in lex:
        cand[str(r["id"])] = {"chunk_id": str(r["id"]), "content": r["content"], "ord": r["ord"],
                              "source_title": r["src"], "source_id": str(r["sid"]),
                              "lex": float(r["sc"] or 0), "vec": 0.0}

    # Vector recall (HNSW cosine); skipped if there is no embed channel
    qvec = None
    try:
        qvec = await model_client.embed_query(db, q, model=embed_model)
    except ModelError as e:
        log.warning("query_embed_failed", error=str(e))
    if qvec:
        vrows = (await db.execute(text("""
            SELECT c.id, c.content, c.ord, r.title AS src, r.id AS sid,
                   1 - (c.embedding <=> (:v)::halfvec) AS sc
            FROM chunks c JOIN raw_sources r ON r.id = c.raw_source_id
            WHERE c.kb_id = :kb AND c.embedding IS NOT NULL
              AND ((:sid)::uuid IS NULL OR c.raw_source_id = (:sid)::uuid)
            ORDER BY c.embedding <=> (:v)::halfvec LIMIT :n
        """), {"kb": str(kb_id), "v": _vec_literal(qvec), "n": _RECALL, "sid": sid})).mappings().all()
        for r in vrows:
            cid = str(r["id"])
            if cid in cand:
                cand[cid]["vec"] = float(r["sc"] or 0)
            else:
                cand[cid] = {"chunk_id": cid, "content": r["content"], "ord": r["ord"],
                             "source_title": r["src"], "source_id": str(r["sid"]),
                             "lex": 0.0, "vec": float(r["sc"] or 0)}

    items = list(cand.values())
    if not items:
        return []

    # Rerank for fine ranking; without a rerank channel, merge by max(vec, lex)
    reranked = None
    try:
        reranked = await model_client.rerank(db, q, [c["content"] for c in items], top_n=limit, model=rerank_model)
    except ModelError as e:
        log.warning("rerank_failed", error=str(e))
    if reranked:
        ordered = [{**items[i], "score": round(s, 4)} for i, s in reranked if i < len(items)]
    else:
        for c in items:
            c["score"] = round(max(c["vec"], c["lex"]), 4)
        ordered = sorted(items, key=lambda c: c["score"], reverse=True)[:limit]

    return [{"chunk_id": c["chunk_id"], "content": c["content"], "ord": c["ord"],
             "source_title": c["source_title"], "source_id": c["source_id"], "score": c["score"]}
            for c in ordered]

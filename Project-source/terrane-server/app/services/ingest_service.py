"""Knowledge base ingestion + hybrid retrieval (platform database terrane_main).

Ingestion: text source -> chunking -> persist -> call the embedding channel to backfill chunks.embedding (halfvec, raw SQL ::halfvec).
Retrieval: dual recall via vector (HNSW cosine) + lexical (pg_trgm) -> merge -> rerank (qwen3-rerank) for fine ranking.
Graceful degradation throughout: no embed channel -> lexical only; no rerank -> merge vector/lexical scores.
"""

from __future__ import annotations

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


def chunk_text(body: str, size: int = _CHUNK_CHARS) -> list[str]:
    """Aggregate paragraphs into chunks of ~size characters (with light overlap to preserve context)."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 1 <= size:
            buf = f"{buf}\n{p}" if buf else p
        else:
            if buf:
                chunks.append(buf)
            if len(p) > size:
                for i in range(0, len(p), size - _OVERLAP):
                    chunks.append(p[i:i + size])
                buf = ""
            else:
                buf = p
    if buf:
        chunks.append(buf)
    return chunks or ([body.strip()] if body.strip() else [])


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


async def _embed_chunks(db: AsyncSession, chunk_ids: list[uuid.UUID], contents: list[str]) -> int:
    """Call the embedding channel to backfill vectors for chunks. No channel -> 0; failure -> logged but does not block ingestion (chunks remain lexically searchable)."""
    try:
        vecs = await model_client.embed_texts(db, contents)
    except ModelError as e:
        log.warning("embed_failed", error=str(e))
        return 0
    if not vecs:
        return 0
    n = 0
    for cid, vec in zip(chunk_ids, vecs):
        await db.execute(text("UPDATE chunks SET embedding = (:v)::halfvec WHERE id = :id"),
                         {"v": _vec_literal(vec), "id": str(cid)})
        n += 1
    return n


async def add_text_source(db: AsyncSession, *, kb_id: uuid.UUID, workspace_id: uuid.UUID,
                          title: str, body: str, kind: str = "text") -> tuple[RawSource, int]:
    """Add a text source -> persist chunks -> backfill vectors. Returns (raw_source, chunk_count)."""
    raw = RawSource(kb_id=kb_id, workspace_id=workspace_id, kind=kind, title=title,
                    mime="text/plain", size_bytes=len(body.encode("utf-8")),
                    status="parsed", parsed_text=body)
    db.add(raw)
    await db.flush()
    pieces = chunk_text(body)
    objs = [Chunk(kb_id=kb_id, raw_source_id=raw.id, ord=i, content=p, token_count=max(1, len(p) // 4))
            for i, p in enumerate(pieces)]
    db.add_all(objs)
    await db.flush()
    embedded = await _embed_chunks(db, [c.id for c in objs], pieces)
    await db.commit()
    await db.refresh(raw)
    log.info("text_source_ingested", kb_id=str(kb_id), raw_id=str(raw.id), chunks=len(pieces), embedded=embedded)
    return raw, len(pieces)


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
    """Write parsed text to an existing source -> clear old chunks -> re-chunk + backfill vectors -> status=parsed. Returns the chunk count."""
    await db.execute(delete(Chunk).where(Chunk.raw_source_id == raw.id))
    raw.parsed_text = body
    raw.status = "parsed"
    raw.error = None
    await db.flush()
    pieces = chunk_text(body)
    objs = [Chunk(kb_id=raw.kb_id, raw_source_id=raw.id, ord=i, content=p, token_count=max(1, len(p) // 4))
            for i, p in enumerate(pieces)]
    db.add_all(objs)
    await db.flush()
    embedded = await _embed_chunks(db, [c.id for c in objs], pieces)
    await db.commit()
    log.info("source_reingested", raw_id=str(raw.id), chunks=len(pieces), embedded=embedded)
    return len(pieces)


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

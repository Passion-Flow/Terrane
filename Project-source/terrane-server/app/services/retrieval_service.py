"""Retrieval 2.0 orchestration.

Fuses up to five recall paths via Reciprocal Rank Fusion (RRF, k=60):
  R1 vector · R2 lexical · R3 reasoning-based tree search · R4 graph multi-hop · R5 RAPTOR semantic tree.
A lightweight Fast/Deep router keeps everyday queries on the millisecond hybrid path and only spends
LLM-driven tree/graph reasoning on complex/structured/cross-document queries. Cross-document candidate
selection (which PageIndex lacks) picks the top-N documents before tree reasoning. Every Deep result
carries a "document > section > page" citation path. All model calls go through the admin channels
(fully on-prem); every path degrades gracefully and never raises.
"""

from __future__ import annotations

import json
import re
import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import graph_service, ingest_service, model_client, tree_service
from app.services.model_client import ModelError

log = structlog.get_logger("terrane.retrieval")

RRF_K = 60
_CAND_DOCS = 4          # cross-document candidate cap
_DEEP_MIN_LEN = 10      # queries this long (chars) lean Deep
_SEMANTIC_MAX_CHUNKS = 2000   # build RAPTOR semantic tree only for KBs up to this size

# Reasoning / structured / question cues (zh + en) → route to Deep. Short keyword lookups stay Fast.
_DEEP_KW = re.compile(
    r"对比|相比|区别|差异|为什么|为何|原因|依据|条款|规定|影响|关系|如何|怎样|怎么|列出|总结|归纳|"
    r"多少|哪些|哪个|是否|能否|可否|需要|流程|申请|步骤|手续|标准|政策|要求|增长|变化|趋势|吗|呢|"
    r"compare|versus|\bvs\b|why|reason|differ|difference|according|clause|impact|relationship|how\s|"
    r"summar|list\s|trend|change|between|process|require|policy|step|should", re.I)


def classify(query: str) -> str:
    """Heuristic Fast/Deep router (no LLM — instant). Deep for question-like / reasoning / structured /
    multi-part queries; Fast for short keyword lookups (cheap millisecond hybrid)."""
    q = query.strip()
    if (len(q) >= _DEEP_MIN_LEN or _DEEP_KW.search(q)
            or q.count("?") + q.count("？") >= 1):
        return "deep"
    return "fast"


def rrf_fuse(lists: list[list[dict]], k: int = RRF_K) -> list[dict]:
    """Reciprocal Rank Fusion over ranked chunk lists, keyed by chunk_id. Merges metadata, preferring a
    citation path when any path supplies one. score(d) = Σ_r 1/(k + rank_r(d))."""
    fused: dict[str, dict] = {}
    for lst in lists:
        for rank, item in enumerate(lst):
            cid = item.get("chunk_id")
            if not cid:
                continue
            slot = fused.get(cid)
            if slot is None:
                slot = {**item, "_rrf": 0.0}
                fused[cid] = slot
            slot["_rrf"] += 1.0 / (k + rank)
            # keep a citation path / page range if this path provides one
            if item.get("citation_path") and not slot.get("citation_path"):
                slot["citation_path"] = item["citation_path"]
                slot["page_start"] = item.get("page_start")
                slot["page_end"] = item.get("page_end")
                slot["node_no"] = item.get("node_no")
    return sorted(fused.values(), key=lambda d: d["_rrf"], reverse=True)


async def cross_doc_select(db: AsyncSession, kb_id: uuid.UUID, query: str, n: int = _CAND_DOCS) -> list[uuid.UUID]:
    """Pick the top-N candidate documents across the whole KB via hybrid recall, RRF-aggregated by source.
    This is the step PageIndex has no answer for (it reasons over one tree at a time)."""
    vec = await ingest_service.recall_vector(db, kb_id=kb_id, query=query, limit=30)
    lex = await ingest_service.recall_lexical(db, kb_id=kb_id, query=query, limit=30)
    agg: dict[str, float] = {}
    for lst in (vec, lex):
        for rank, item in enumerate(lst):
            sid = item.get("source_id")
            if sid:
                agg[sid] = agg.get(sid, 0.0) + 1.0 / (RRF_K + rank)
    top = sorted(agg.items(), key=lambda x: x[1], reverse=True)[:n]
    out = []
    for sid, _ in top:
        try:
            out.append(uuid.UUID(sid))
        except ValueError:
            continue
    return out


async def attach_citations(db: AsyncSession, items: list[dict]) -> None:
    """Backfill citation path / page range for items that lack one, via chunk.tree_node_id → doc_tree_nodes."""
    need = [it["chunk_id"] for it in items if it.get("chunk_id") and not it.get("citation_path")]
    if not need:
        return
    rows = (await db.execute(text("""
        SELECT c.id AS cid, n.path_titles, n.page_start, n.page_end, n.node_no
        FROM chunks c JOIN doc_tree_nodes n ON n.id = c.tree_node_id
        WHERE c.id = ANY(:ids)
    """), {"ids": need})).mappings().all()
    by_cid = {str(r["cid"]): r for r in rows}
    for it in items:
        r = by_cid.get(it.get("chunk_id"))
        if r:
            it["citation_path"] = r["path_titles"] or None
            it["page_start"] = r["page_start"]
            it["page_end"] = r["page_end"]
            it["node_no"] = r["node_no"]


# ---------------------------------------------------------------- RAPTOR semantic tree (R5)

def _parse_vec(s: str) -> list[float]:
    return [float(x) for x in s.strip().strip("[]").split(",") if x]


async def build_semantic_tree(db: AsyncSession, kb_id: uuid.UUID) -> int:
    """RAPTOR-style: cluster the KB's chunk embeddings, summarize each cluster into a semantic node
    (embedding + covered chunk ids). Bounded + best-effort; needs numpy + embeddings + chat channel."""
    try:
        import numpy as np
    except Exception:  # noqa: BLE001
        return 0
    rows = (await db.execute(text("""
        SELECT id, content, embedding::text AS vec FROM chunks
        WHERE kb_id = :kb AND embedding IS NOT NULL
    """), {"kb": str(kb_id)})).mappings().all()
    if len(rows) < 8 or len(rows) > _SEMANTIC_MAX_CHUNKS:
        return 0
    try:
        mat = np.array([_parse_vec(r["vec"]) for r in rows], dtype="float32")
    except Exception:  # noqa: BLE001
        return 0
    k = max(2, min(12, len(rows) // 10))
    # tiny KMeans (cosine ≈ normalized L2), few iterations, numpy only
    norm = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8)
    rng = np.random.default_rng(42)
    cent = norm[rng.choice(len(norm), k, replace=False)]
    labels = np.zeros(len(norm), dtype="int32")
    for _ in range(10):
        sims = norm @ cent.T
        labels = sims.argmax(axis=1)
        for ci in range(k):
            members = norm[labels == ci]
            if len(members):
                cent[ci] = members.mean(axis=0)
        cent = cent / (np.linalg.norm(cent, axis=1, keepdims=True) + 1e-8)
    await db.execute(text("DELETE FROM doc_tree_nodes WHERE kb_id = :kb AND kind = 'semantic'"), {"kb": str(kb_id)})
    made = 0
    for ci in range(k):
        idx = [i for i in range(len(rows)) if labels[i] == ci]
        if not idx:
            continue
        cluster_text = "\n\n".join(rows[i]["content"][:400] for i in idx[:12])
        try:
            summary = await model_client.chat_complete(db, [{"role": "user", "content":
                "用 2-3 句话概括下面这组资料的共同主题与关键信息(用资料的语言):\n\n" + cluster_text[:4000]}],
                temperature=0.2, max_tokens=300)
        except ModelError:
            summary = cluster_text[:240]
        nid = uuid.uuid4()
        covered = [str(rows[i]["id"]) for i in idx]
        await db.execute(text("""
            INSERT INTO doc_tree_nodes (id, kb_id, raw_source_id, parent_id, kind, node_no, depth, ord,
                title, summary, token_count, path_titles, meta)
            VALUES (:id,:kb,NULL,NULL,'semantic',:no,1,:ord,:title,:summary,0,'[]'::jsonb,
                CAST(:meta AS jsonb))
        """), {"id": str(nid), "kb": str(kb_id), "no": f"S{ci:03d}", "ord": ci,
               "title": f"主题簇 {ci + 1}", "summary": (summary or "").strip()[:1200],
               "meta": json.dumps({"covered_chunks": covered})})
        try:
            vecs = await model_client.embed_texts(db, [summary or ""])
            if vecs:
                await db.execute(text("UPDATE doc_tree_nodes SET embedding=(:v)::halfvec WHERE id=:id"),
                                 {"v": tree_service._vec_literal(vecs[0]), "id": str(nid)})
        except (ModelError, Exception):  # noqa: BLE001
            pass
        made += 1
    await db.commit()
    log.info("semantic_tree_built", kb=str(kb_id), clusters=made, chunks=len(rows))
    return made


async def recall_semantic(db: AsyncSession, kb_id: uuid.UUID, query: str, limit: int = 12) -> list[dict]:
    """R5: match the query against semantic-cluster nodes, return their covered chunks (global/multi-hop concepts)."""
    try:
        qvec = await model_client.embed_query(db, query)
    except ModelError:
        return []
    if not qvec:
        return []
    nodes = (await db.execute(text("""
        SELECT meta FROM doc_tree_nodes
        WHERE kb_id = :kb AND kind = 'semantic' AND embedding IS NOT NULL
        ORDER BY embedding <=> (:v)::halfvec LIMIT 3
    """), {"kb": str(kb_id), "v": ingest_service._vec_literal(qvec)})).mappings().all()
    cids: list[str] = []
    for nd in nodes:
        cids.extend((nd["meta"] or {}).get("covered_chunks", [])[:8])
    if not cids:
        return []
    rows = (await db.execute(text("""
        SELECT c.id, c.content, c.ord, r.title AS src, r.id AS sid
        FROM chunks c JOIN raw_sources r ON r.id = c.raw_source_id
        WHERE c.id = ANY(:ids) LIMIT :n
    """), {"ids": cids[:limit * 2], "n": limit})).mappings().all()
    return [{"chunk_id": str(r["id"]), "content": r["content"], "ord": r["ord"],
             "source_title": r["src"], "source_id": str(r["sid"]), "score": 0.0} for r in rows]


# ---------------------------------------------------------------- top-level entry

async def retrieve(db: AsyncSession, *, kb_id: uuid.UUID, query: str, mode: str = "auto", limit: int = 8,
                   source_id: uuid.UUID | None = None, embed_model: str | None = None,
                   rerank_model: str | None = None) -> list[dict]:
    """Unified retrieval. mode: fast | deep | auto. Returns ranked chunk dicts with optional citation path."""
    q = query.strip()
    if not q:
        return []
    eff = classify(q) if (mode or "auto") == "auto" else mode

    # Fast path = the existing fused hybrid (vector+lexical+rerank); add citations for explainability.
    if eff == "fast":
        hits = await ingest_service.search_chunks(db, kb_id=kb_id, query=q, limit=limit,
                                                  embed_model=embed_model, rerank_model=rerank_model,
                                                  raw_source_id=source_id)
        await attach_citations(db, hits)
        for h in hits:
            h["mode"] = "fast"
        return hits

    # Deep path: cross-doc routing → R1..R5 → RRF → rerank → citations.
    source_ids = [source_id] if source_id else await cross_doc_select(db, kb_id, q, _CAND_DOCS)
    r1 = await ingest_service.recall_vector(db, kb_id=kb_id, query=q, limit=20, source_ids=source_ids or None, embed_model=embed_model)
    r2 = await ingest_service.recall_lexical(db, kb_id=kb_id, query=q, limit=20, source_ids=source_ids or None)
    r3 = await tree_service.tree_search(db, kb_id=kb_id, query=q, source_ids=source_ids) if source_ids else []
    r4 = await graph_service.multihop(db, kb_id, q)
    r5 = await recall_semantic(db, kb_id, q)

    fused = rrf_fuse([r1, r2, r3, r4, r5])
    if not fused:
        # nothing fused (e.g. empty KB) → fall back to fast
        return await retrieve(db, kb_id=kb_id, query=q, mode="fast", limit=limit, source_id=source_id,
                              embed_model=embed_model, rerank_model=rerank_model)

    cand = fused[:max(limit * 3, 20)]
    # fine rerank over fused candidates (degrade to RRF order if no rerank channel)
    try:
        reranked = await model_client.rerank(db, q, [c["content"] for c in cand], top_n=limit, model=rerank_model)
    except ModelError:
        reranked = None
    if reranked:
        ordered = [{**cand[i], "score": round(s, 4)} for i, s in reranked if i < len(cand)]
    else:
        ordered = [{**c, "score": round(c["_rrf"], 4)} for c in cand[:limit]]

    # defensive dedup by chunk_id (a chunk may surface from several recall paths)
    seen: set[str] = set()
    deduped: list[dict] = []
    for h in ordered:
        cid = h.get("chunk_id")
        if cid in seen:
            continue
        seen.add(cid)
        h["mode"] = "deep"
        h.pop("_rrf", None)
        h.pop("_tree_rank", None)
        deduped.append(h)
    await attach_citations(db, deduped)
    return deduped[:limit]

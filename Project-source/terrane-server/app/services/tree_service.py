"""Retrieval 2.0 — structural ToC tree index + reasoning-based tree search (PageIndex-style, but stronger).

build_tree(db, raw): parse the source's parsed Markdown into a heading hierarchy (root = the whole doc;
fallback = single root when there are no headings), derive each node's page range from the
``<!-- Page N -->`` markers emitted by the VL parser, persist doc_tree_nodes, back-link every chunk to its
deepest containing node (chunks.tree_node_id), and embed title+snippet for vector candidate routing.

tree_search(db, kb_id, query, source_ids): an LLM greedily descends each document's tree (beam width +
a hard max_llm_calls guardrail that PageIndex lacks), selects the most relevant sections, and returns the
chunks beneath them with a "document > section > page" citation path. Falls back to nothing (the caller
fuses with vector/lexical), never raising.
"""

from __future__ import annotations

import json
import re
import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb_content import RawSource
from app.services import model_client
from app.services.model_client import ModelError

log = structlog.get_logger("terrane.tree")

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.M)
_PAGE_RE = re.compile(r"<!--\s*Page\s+(\d+)\s*-->", re.I)
_SNIPPET = 240            # pseudo-summary length (chars) — cheap, deterministic, no ingest-time LLM cost
_MAX_NODES = 600         # per-doc node cap (very large docs)

# ---- functional model-navigation prompt (kept Chinese per project convention) ----
_SELECT_PROMPT = (
    "你在按「目录」为给定问题定位最相关的章节。只能依据下面给的「编号 标题 — 摘要」,不要臆测正文。\n"
    "为每个看起来相关的候选给出:node(编号)、action(stop=答案很可能就在此节点 / descend=应进入其子节点)、"
    "score(0~1 相关度)。最多挑 {beam} 个最相关的;都不相关就返回空数组。只输出 JSON 数组,"
    "形如 [{{\"node\":\"0006\",\"action\":\"descend\",\"score\":0.8}}]。\n\n问题:{query}\n\n候选节点:\n{cands}"
)


def _clean(md_slice: str) -> str:
    """Strip heading markers / page markers / image tags to make a readable snippet."""
    s = _PAGE_RE.sub(" ", md_slice)
    s = re.sub(r"^#{1,6}\s+", "", s, flags=re.M)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_structure(md: str, root_title: str) -> list[dict]:
    """Parse Markdown headings into a node list (adjacency via parent_idx). Node 0 is the doc root."""
    pages = [(m.start(), int(m.group(1))) for m in _PAGE_RE.finditer(md)]

    def page_at(pos: int) -> int | None:
        pg = None
        for cp, p in pages:
            if cp <= pos:
                pg = p
            else:
                break
        return pg

    n = len(md)
    nodes: list[dict] = [{
        "level": 0, "title": root_title[:300] or "Document", "char_start": 0, "char_end": n,
        "parent_idx": None, "page_start": pages[0][1] if pages else None,
        "page_end": pages[-1][1] if pages else None,
    }]
    headings = [(m.start(), len(m.group(1)), m.group(2).strip()) for m in _HEADING_RE.finditer(md)]
    stack = [0]  # indices into nodes
    for i, (start, level, title) in enumerate(headings):
        if len(nodes) >= _MAX_NODES:
            break
        end = n
        for s2, l2, _t in headings[i + 1:]:
            if l2 <= level:
                end = s2
                break
        while len(stack) > 1 and nodes[stack[-1]]["level"] >= level:
            stack.pop()
        nodes.append({
            "level": level, "title": (title or "Section")[:300], "char_start": start, "char_end": end,
            "parent_idx": stack[-1], "page_start": page_at(start), "page_end": page_at(max(start, end - 1)),
        })
        stack.append(len(nodes) - 1)
    return nodes


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


async def build_tree(db: AsyncSession, raw: RawSource) -> int:
    """Build (or rebuild) the structural tree for one source. Returns node count. Best-effort: never raises."""
    md = raw.parsed_text or ""
    if not md.strip():
        return 0
    try:
        await db.execute(text("DELETE FROM doc_tree_nodes WHERE raw_source_id = :s AND kind = 'structural'"),
                         {"s": str(raw.id)})
        nodes = _parse_structure(md, raw.title)
        # assign ids, depth, ord, node_no, path_titles, snippet summary
        ids = [uuid.uuid4() for _ in nodes]
        for i, nd in enumerate(nodes):
            nd["id"] = ids[i]
            nd["ord"] = i
            nd["node_no"] = f"{i:04d}"
            body = _clean(md[nd["char_start"]:nd["char_end"]])
            # drop the title itself from the front of the snippet
            if body.lower().startswith(nd["title"].lower()):
                body = body[len(nd["title"]):].strip()
            nd["summary"] = body[:_SNIPPET]
            nd["token_count"] = max(1, (nd["char_end"] - nd["char_start"]) // 4)
        # path_titles (ancestor chain, excluding root's generic title is fine to include)
        for nd in nodes:
            path, cur = [], nd
            while cur is not None:
                path.append(cur["title"])
                cur = nodes[cur["parent_idx"]] if cur["parent_idx"] is not None else None
            nd["path_titles"] = list(reversed(path))
        # persist
        for nd in nodes:
            await db.execute(text("""
                INSERT INTO doc_tree_nodes
                  (id, kb_id, raw_source_id, parent_id, kind, node_no, depth, ord, title, summary,
                   page_start, page_end, char_start, char_end, token_count, path_titles)
                VALUES (:id,:kb,:src,:parent,'structural',:no,:depth,:ord,:title,:summary,
                   :ps,:pe,:cs,:ce,:tc, CAST(:paths AS jsonb))
            """), {
                "id": str(nd["id"]), "kb": str(raw.kb_id), "src": str(raw.id),
                "parent": str(nodes[nd["parent_idx"]]["id"]) if nd["parent_idx"] is not None else None,
                "no": nd["node_no"], "depth": nd["level"], "ord": nd["ord"],
                "title": nd["title"], "summary": nd["summary"],
                "ps": nd["page_start"], "pe": nd["page_end"],
                "cs": nd["char_start"], "ce": nd["char_end"], "tc": nd["token_count"],
                "paths": json.dumps(nd["path_titles"], ensure_ascii=False),
            })
        # embed title+summary (best-effort)
        try:
            texts = [f"{nd['title']}\n{nd['summary']}" for nd in nodes]
            vecs = await model_client.embed_texts(db, texts)
            if vecs:
                for nd, v in zip(nodes, vecs):
                    await db.execute(text("UPDATE doc_tree_nodes SET embedding = (:v)::halfvec WHERE id = :id"),
                                     {"v": _vec_literal(v), "id": str(nd["id"])})
        except (ModelError, Exception) as e:  # noqa: BLE001
            log.warning("tree_embed_failed", error=str(e))
        # back-link chunks to deepest containing node (by content position in parsed_text)
        rows = (await db.execute(text(
            "SELECT id, content FROM chunks WHERE raw_source_id = :s"), {"s": str(raw.id)})).mappings().all()
        for r in rows:
            probe = (r["content"] or "")[:60]
            pos = md.find(probe) if probe else -1
            node_id = None
            if pos >= 0:
                best = None
                for nd in nodes:
                    if nd["char_start"] <= pos < nd["char_end"]:
                        if best is None or nd["level"] > best["level"]:
                            best = nd
                node_id = str(best["id"]) if best else str(nodes[0]["id"])
            else:
                node_id = str(nodes[0]["id"])
            await db.execute(text("UPDATE chunks SET tree_node_id = :n WHERE id = :id"),
                             {"n": node_id, "id": str(r["id"])})
        await db.commit()
        log.info("tree_built", raw_id=str(raw.id), nodes=len(nodes))
        return len(nodes)
    except Exception as e:  # noqa: BLE001
        log.warning("tree_build_failed", raw_id=str(raw.id), error=str(e))
        await db.rollback()
        return 0


async def _load_nodes(db: AsyncSession, source_ids: list[uuid.UUID]) -> dict[str, list[dict]]:
    """Load structural nodes grouped by source: {source_id: [node, ...]} with children index."""
    if not source_ids:
        return {}
    rows = (await db.execute(text("""
        SELECT id, raw_source_id, parent_id, node_no, depth, title, summary, page_start, page_end, path_titles
        FROM doc_tree_nodes WHERE kind='structural' AND raw_source_id = ANY(:ids) ORDER BY ord
    """), {"ids": [str(s) for s in source_ids]})).mappings().all()
    by_src: dict[str, list[dict]] = {}
    for r in rows:
        by_src.setdefault(str(r["raw_source_id"]), []).append(dict(r))
    return by_src


def _children(nodes: list[dict], parent_id) -> list[dict]:
    pid = str(parent_id) if parent_id else None
    return [n for n in nodes if (str(n["parent_id"]) if n["parent_id"] else None) == pid]


def _descendants(nodes: list[dict], node_id) -> list[str]:
    """All descendant node ids (inclusive) of node_id, in-memory."""
    out, frontier = [str(node_id)], [str(node_id)]
    while frontier:
        cur = frontier.pop()
        for c in nodes:
            if (str(c["parent_id"]) if c["parent_id"] else None) == cur:
                cid = str(c["id"])
                out.append(cid)
                frontier.append(cid)
    return out


async def _llm_select(db: AsyncSession, query: str, cands: list[dict], beam: int) -> list[dict]:
    """Ask the chat model to pick the most relevant candidate nodes. Returns [{node, action, score}]."""
    listing = "\n".join(f"{c['node_no']}  {c['title']} — {(c.get('summary') or '')[:160]}" for c in cands)
    prompt = _SELECT_PROMPT.format(beam=beam, query=query[:500], cands=listing[:6000])
    try:
        raw = await model_client.chat_complete(db, [{"role": "user", "content": prompt}],
                                                temperature=0.0, max_tokens=400)
    except ModelError:
        return []
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", raw).strip()
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return []
    try:
        picks = json.loads(m.group(0))
        return [p for p in picks if isinstance(p, dict) and p.get("node")]
    except ValueError:
        return []


async def tree_search(db: AsyncSession, *, kb_id: uuid.UUID, query: str, source_ids: list[uuid.UUID],
                      beam: int = 2, max_llm_calls: int = 6, max_select: int = 8) -> list[dict]:
    """Reasoning-based navigation across the given documents' trees. Returns ranked chunk dicts with
    citation paths. Hard guardrail: total LLM calls <= max_llm_calls (keeps latency/cost bounded —
    PageIndex has no such cap). Never raises; empty result lets the caller fuse with vector/lexical."""
    q = query.strip()
    if not q or not source_ids:
        return []
    by_src = await _load_nodes(db, source_ids)
    if not by_src:
        return []
    calls_left = max_llm_calls
    per_src = max(1, max_llm_calls // max(1, len(by_src)))
    selected: list[dict] = []  # {node, source_id}
    for sid, nodes in by_src.items():
        if calls_left <= 0:
            break
        budget = min(per_src, calls_left)
        roots = [n for n in nodes if n["depth"] == 0]
        # frontier = children of root (top-level sections); if none, take root itself
        frontier = _children(nodes, roots[0]["id"]) if roots else []
        if not frontier:
            if roots:
                selected.append({"node": roots[0], "source_id": sid})
            continue
        local_calls = 0
        while frontier and local_calls < budget and len(selected) < max_select:
            picks = await _llm_select(db, q, frontier[:30], beam)
            local_calls += 1
            calls_left -= 1
            if not picks:
                break
            next_frontier: list[dict] = []
            for p in sorted(picks, key=lambda x: -float(x.get("score") or 0))[:beam]:
                node = next((n for n in frontier if n["node_no"] == str(p.get("node"))), None)
                if node is None:
                    continue
                kids = _children(nodes, node["id"])
                if p.get("action") == "descend" and kids:
                    next_frontier.extend(kids)
                else:
                    selected.append({"node": node, "source_id": sid})
            frontier = next_frontier
            if calls_left <= 0:
                break
        # if descended to leaves without an explicit stop, keep the last frontier as selected
        for n in frontier[:beam]:
            if len(selected) < max_select:
                selected.append({"node": n, "source_id": sid})

    if not selected:
        return []
    # map selected nodes -> chunks under their subtrees, attach citation
    out: list[dict] = []
    seen: set[str] = set()
    for rank, sel in enumerate(selected):
        node = sel["node"]
        nodes = by_src[sel["source_id"]]
        node_ids = _descendants(nodes, node["id"])
        rows = (await db.execute(text("""
            SELECT c.id, c.content, c.ord, r.title AS src, r.id AS sid
            FROM chunks c JOIN raw_sources r ON r.id = c.raw_source_id
            WHERE c.tree_node_id = ANY(:nids) ORDER BY c.ord LIMIT 12
        """), {"nids": node_ids})).mappings().all()
        path = node.get("path_titles") or [node["title"]]
        for r in rows:
            cid = str(r["id"])
            if cid in seen:
                continue
            seen.add(cid)
            out.append({
                "chunk_id": cid, "content": r["content"], "ord": r["ord"],
                "source_title": r["src"], "source_id": str(r["sid"]),
                "citation_path": path, "page_start": node.get("page_start"), "page_end": node.get("page_end"),
                "node_no": node["node_no"], "_tree_rank": len(out),
            })
    log.info("tree_search", kb=str(kb_id), sources=len(by_src), selected=len(selected), chunks=len(out))
    return out

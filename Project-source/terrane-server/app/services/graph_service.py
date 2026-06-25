"""Knowledge graph (AGE, platform database terrane_main). One graph per KB, named kb_<hex>.

An LLM (qwen3.7-plus) extracts entities/relations from text -> MERGE into the AGE graph. The graph is the source of truth; the wiki is a projection of it (later).
AGE's `:Label` cypher syntax conflicts with SQLAlchemy's `:bind` -> execute cypher directly over the underlying asyncpg connection.
"""

from __future__ import annotations

import json
import re
import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import model_client
from app.services.model_client import ModelError

log = structlog.get_logger("terrane.graph")

_EXTRACT_PROMPT = (
    "你是知识图谱抽取器。从下面文本中抽取实体与有向关系,只输出 JSON,不要任何解释或 markdown 代码块。\n"
    "格式:{\"entities\":[{\"name\":\"实体名\",\"type\":\"类型\"}],"
    "\"relations\":[{\"source\":\"实体A\",\"target\":\"实体B\",\"type\":\"关系\"}]}\n"
    "要求:实体名简洁规范(去掉修饰词),关系动词化且有向,只抽取文本明确表达的事实。\n\n文本:\n"
)
_MAX_TEXT = 2400


def graph_name(kb_id: uuid.UUID) -> str:
    return "kb_" + kb_id.hex


def _san(s: str, n: int = 100) -> str:
    """Sanitize entity/relation names to avoid cypher injection: strip quotes/backslashes/newlines, then truncate."""
    s = re.sub(r"[\\'\"\n\r]", " ", str(s)).strip()
    return s[:n]


async def _ac(db: AsyncSession):
    """Get the underlying asyncpg connection and load AGE (same transaction, so db.commit() takes effect)."""
    conn = await db.connection()
    raw = await conn.get_raw_connection()
    ac = raw.driver_connection
    await ac.execute("LOAD 'age'")
    await ac.execute('SET search_path = ag_catalog, "$user", public')
    return ac


async def ensure_graph(db: AsyncSession, kb_id: uuid.UUID) -> str:
    g = graph_name(kb_id)
    ac = await _ac(db)
    exists = await ac.fetchval("SELECT count(*) FROM ag_catalog.ag_graph WHERE name = $1", g)
    if not exists:
        await ac.execute(f"SELECT create_graph('{g}')")
    return g


async def drop_graph(db: AsyncSession, kb_id: uuid.UUID) -> None:
    """Drop this KB's AGE graph (cleanup after deleting a source / clearing the old one before a rebuild). Idempotent."""
    g = graph_name(kb_id)
    ac = await _ac(db)
    exists = await ac.fetchval("SELECT count(*) FROM ag_catalog.ag_graph WHERE name = $1", g)
    if exists:
        await ac.execute(f"SELECT drop_graph('{g}', true)")  # true = cascade-delete labels/data


def _parse_extraction(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", raw).strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {"entities": [], "relations": []}
    try:
        d = json.loads(m.group(0))
        return {"entities": d.get("entities", []) or [], "relations": d.get("relations", []) or []}
    except ValueError:
        return {"entities": [], "relations": []}


async def build_from_text(db: AsyncSession, kb_id: uuid.UUID, content: str) -> tuple[int, int]:
    """Extract from a piece of text and MERGE into the graph. Returns (entity count, relation count)."""
    g = await ensure_graph(db, kb_id)
    text_in = content[:_MAX_TEXT]
    try:
        raw = await model_client.chat_complete(
            db, [{"role": "user", "content": _EXTRACT_PROMPT + text_in}], temperature=0.0, max_tokens=1500)
    except ModelError as e:
        log.warning("extract_failed", error=str(e))
        return 0, 0
    data = _parse_extraction(raw)
    ac = await _ac(db)
    ents = 0
    for e in data["entities"]:
        name = _san(e.get("name", ""))
        if not name:
            continue
        etype = _san(e.get("type", "Entity"), 40) or "Entity"
        await ac.execute(
            f"SELECT * FROM cypher('{g}', $$ MERGE (n:Entity {{name:'{name}'}}) "
            f"SET n.etype='{etype}' RETURN n $$) AS (n agtype)")
        ents += 1
    rels = 0
    for r in data["relations"]:
        a, b = _san(r.get("source", "")), _san(r.get("target", ""))
        rt = _san(r.get("type", "相关"), 60) or "相关"
        if not a or not b:
            continue
        await ac.execute(
            f"SELECT * FROM cypher('{g}', $$ MERGE (a:Entity {{name:'{a}'}}) "
            f"MERGE (b:Entity {{name:'{b}'}}) MERGE (a)-[e:REL {{type:'{rt}'}}]->(b) "
            f"RETURN e $$) AS (e agtype)")
        rels += 1
    return ents, rels


async def build_graph(db: AsyncSession, kb_id: uuid.UUID, sources: list[tuple[str, str]]) -> dict:
    """Build the graph from a set of (title, text) sources. sources are already fetched by the caller (to avoid streaming lifecycle issues)."""
    total_e = total_r = 0
    for _title, txt in sources:
        if not txt or not txt.strip():
            continue
        e, r = await build_from_text(db, kb_id, txt)
        total_e += e
        total_r += r
    await db.commit()
    log.info("graph_built", kb_id=str(kb_id), entities=total_e, relations=total_r)
    return {"entities_added": total_e, "relations_added": total_r}


_ENTITY_PROMPT = (
    "从下面问题中抽取出最关键的实体名(人名/机构/产品/概念等),只输出 JSON 数组,"
    "如 [\"实体A\",\"实体B\"];没有就返回 []。\n\n问题:"
)


async def multihop(db: AsyncSession, kb_id: uuid.UUID, query: str, *, hops: int = 2, limit: int = 12) -> list[dict]:
    """Graph multi-hop recall (Retrieval 2.0 R4): extract entities from the query -> expand 1-2 hops in the
    KB's AGE graph -> map neighbour entity names back to chunks (lexical). Returns ranked chunk dicts.
    Best-effort: no graph / no chat channel / no matches -> []. PageIndex has no equivalent."""
    g = graph_name(kb_id)
    try:
        ac = await _ac(db)
        if not await ac.fetchval("SELECT count(*) FROM ag_catalog.ag_graph WHERE name = $1", g):
            return []
        raw = await model_client.chat_complete(
            db, [{"role": "user", "content": _ENTITY_PROMPT + query[:400]}], temperature=0.0, max_tokens=200)
    except (ModelError, Exception) as e:  # noqa: BLE001
        log.warning("multihop_entity_failed", error=str(e))
        return []
    m = re.search(r"\[.*\]", raw.strip(), re.S)
    if not m:
        return []
    try:
        seeds = [_san(x) for x in json.loads(m.group(0)) if str(x).strip()]
    except ValueError:
        return []
    if not seeds:
        return []
    # expand neighbours up to `hops`
    names: set[str] = set(seeds)
    try:
        for seed in seeds[:6]:
            rows = await ac.fetch(
                f"SELECT b FROM cypher('{g}', $$ MATCH (a:Entity {{name:'{seed}'}})-[*1..{max(1, hops)}]-(b:Entity) "
                f"RETURN DISTINCT b.name $$) AS (b agtype) LIMIT 40")
            for r in rows:
                try:
                    names.add(_san(json.loads(str(r["b"]))))
                except (ValueError, TypeError):
                    continue
    except Exception as e:  # noqa: BLE001
        log.warning("multihop_expand_failed", error=str(e))
    names = {n for n in names if n}
    if not names:
        return []
    # map entity names back to chunks (rank by number of distinct matched entities)
    name_list = list(names)[:40]
    conds = " OR ".join(f"c.content ILIKE :p{i}" for i in range(len(name_list)))
    params = {f"p{i}": f"%{n}%" for i, n in enumerate(name_list)}
    score_expr = " + ".join(f"(c.content ILIKE :p{i})::int" for i in range(len(name_list)))
    rows = (await db.execute(text(f"""
        SELECT c.id, c.content, c.ord, r.title AS src, r.id AS sid, ({score_expr}) AS hits
        FROM chunks c JOIN raw_sources r ON r.id = c.raw_source_id
        WHERE c.kb_id = :kb AND ({conds})
        ORDER BY hits DESC LIMIT :n
    """), {"kb": str(kb_id), "n": limit, **params})).mappings().all()
    return [{"chunk_id": str(r["id"]), "content": r["content"], "ord": r["ord"],
             "source_title": r["src"], "source_id": str(r["sid"]), "score": float(r["hits"] or 0)} for r in rows]


async def graph_data(db: AsyncSession, kb_id: uuid.UUID, limit: int = 300) -> dict:
    """Fetch the graph's nodes + edges for visualization."""
    g = graph_name(kb_id)
    ac = await _ac(db)
    exists = await ac.fetchval("SELECT count(*) FROM ag_catalog.ag_graph WHERE name = $1", g)
    if not exists:
        return {"nodes": [], "edges": []}
    nrows = await ac.fetch(
        f"SELECT n FROM cypher('{g}', $$ MATCH (n:Entity) RETURN n LIMIT {limit} $$) AS (n agtype)")
    nodes = []
    for row in nrows:
        v = json.loads(str(row["n"]).replace("::vertex", ""))
        props = v.get("properties", {})
        nodes.append({"id": str(v.get("id")), "name": props.get("name", ""), "etype": props.get("etype", "Entity")})
    erows = await ac.fetch(
        f"SELECT a,r,b FROM cypher('{g}', $$ MATCH (a)-[r:REL]->(b) RETURN a.name, r.type, b.name "
        f"LIMIT {limit} $$) AS (a agtype, r agtype, b agtype)")
    edges = []
    for row in erows:
        edges.append({"source": json.loads(str(row["a"])), "type": json.loads(str(row["r"])),
                      "target": json.loads(str(row["b"]))})
    return {"nodes": nodes, "edges": edges}

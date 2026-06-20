"""知识图谱（AGE，平台库 terrane_main）。每库一张图 kb_<hex>。

LLM(qwen3.7-plus)从文本抽实体/关系 → MERGE 进 AGE 图。图是权威源,wiki 是其投影(后续)。
AGE 的 `:Label` cypher 语法与 SQLAlchemy `:bind` 冲突 → 走底层 asyncpg 连接直执行 cypher。
"""

from __future__ import annotations

import json
import re
import uuid

import structlog
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
    """清洗实体/关系名,避免 cypher 注入:去引号/反斜杠/换行,截断。"""
    s = re.sub(r"[\\'\"\n\r]", " ", str(s)).strip()
    return s[:n]


async def _ac(db: AsyncSession):
    """取底层 asyncpg 连接并装载 AGE(同一事务,db.commit() 生效)。"""
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
    """删除该库的 AGE 图(删源后清理 / 重建前清旧)。幂等。"""
    g = graph_name(kb_id)
    ac = await _ac(db)
    exists = await ac.fetchval("SELECT count(*) FROM ag_catalog.ag_graph WHERE name = $1", g)
    if exists:
        await ac.execute(f"SELECT drop_graph('{g}', true)")  # true = 级联删标签/数据


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
    """对一段文本抽取并 MERGE 进图。返回 (实体数, 关系数)。"""
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
    """对一组 (title, text) 源构建图。sources 已由调用方取好(避免流式生命周期问题)。"""
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


async def graph_data(db: AsyncSession, kb_id: uuid.UUID, limit: int = 300) -> dict:
    """取图的节点 + 边,供可视化。"""
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

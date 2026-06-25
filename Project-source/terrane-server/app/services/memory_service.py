"""Memory system (platform DB terrane_main) — per-user memory write / semantic recall / LLM extraction.

Hard rule: every query is filtered by user_id and **never crosses users**. Embeddings use raw SQL (::halfvec).
"""

from __future__ import annotations

import json
import re
import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.services import model_client
from app.services.model_client import ModelError

log = structlog.get_logger("terrane.memory")

_EXTRACT_PROMPT = (
    "从下面文本中抽取关于「用户本人」值得长期记住的个人记忆(偏好/事实/重要事件),"
    "只输出 JSON 数组,格式 [{\"content\":\"...\",\"kind\":\"fact|preference|event\"}],没有就输出 []。"
    "不要抽取与用户无关的常识。\n\n文本:\n"
)


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


async def remember(db: AsyncSession, user_id: uuid.UUID, content: str, *,
                   kind: str = "fact", source: str = "manual") -> Memory:
    m = Memory(id=uuid.uuid4(), user_id=user_id, content=content, kind=kind, source=source)
    db.add(m)
    await db.flush()
    try:
        vecs = await model_client.embed_texts(db, [content])
        if vecs:
            await db.execute(text("UPDATE memories SET embedding = (:v)::halfvec WHERE id = :id"),
                             {"v": _vec(vecs[0]), "id": str(m.id)})
    except ModelError as e:
        log.warning("memory_embed_failed", error=str(e))
    await db.commit()
    await db.refresh(m)
    return m


async def recall(db: AsyncSession, user_id: uuid.UUID, query: str, limit: int = 5) -> list[dict]:
    """Semantically recall the current user's memories (vector first, falling back to trgm). Strictly filtered by user_id."""
    q = query.strip()
    if not q:
        return []
    qvec = None
    try:
        qvec = await model_client.embed_query(db, q)
    except ModelError:
        qvec = None
    if qvec:
        rows = (await db.execute(text("""
            SELECT id, content, kind, 1 - (embedding <=> (:v)::halfvec) AS sc
            FROM memories WHERE user_id = :uid AND embedding IS NOT NULL
            ORDER BY embedding <=> (:v)::halfvec LIMIT :n
        """), {"uid": str(user_id), "v": _vec(qvec), "n": limit})).mappings().all()
    else:
        rows = (await db.execute(text("""
            SELECT id, content, kind, similarity(content, :q) AS sc
            FROM memories WHERE user_id = :uid AND (content ILIKE :like OR similarity(content, :q) > 0.05)
            ORDER BY sc DESC LIMIT :n
        """), {"uid": str(user_id), "q": q, "like": f"%{q}%", "n": limit})).mappings().all()
    return [{"id": str(r["id"]), "content": r["content"], "kind": r["kind"],
             "score": round(float(r["sc"] or 0), 4)} for r in rows]


def _parse_ops(raw: str) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", raw).strip()
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return []
    try:
        v = json.loads(m.group(0))
        return v if isinstance(v, list) else []
    except ValueError:
        return []


async def _update_memory(db: AsyncSession, mem_id: str, content: str, kind: str) -> None:
    m = await db.get(Memory, uuid.UUID(mem_id))
    if m is None:
        return
    m.content = content
    if kind in ("fact", "preference", "event"):
        m.kind = kind
    await db.flush()
    try:
        vecs = await model_client.embed_texts(db, [content])
        if vecs:
            await db.execute(text("UPDATE memories SET embedding=(:v)::halfvec WHERE id=:id"),
                             {"v": _vec(vecs[0]), "id": mem_id})
    except ModelError:
        pass
    await db.commit()


_CONSOLIDATE_PROMPT = (
    "你在维护『用户本人』的长期个人记忆库。下面给出用户【已有记忆】和一段【新内容】。\n"
    "从【新内容】中找出关于用户本人值得长期记住的信息(个人偏好/事实/重要事件/长期目标/习惯),"
    "与【已有记忆】比对后,只输出操作 JSON 数组(不要任何多余文字):\n"
    '[{"op":"ADD","content":"完整独立的一句话","kind":"fact|preference|event"} '
    '| {"op":"UPDATE","id":"已有记忆的id","content":"修正或补充后的完整内容","kind":"..."}]\n'
    "规则:① 与已有记忆重复的不要输出;② 矛盾或更精确的用 UPDATE 对应 id;③ 全新的用 ADD;"
    "④ 与用户本人无关的常识、资料正文、一次性临时内容都不要记;⑤ 没有可记的就输出 []。\n\n"
)


async def consolidate(db: AsyncSession, user_id: uuid.UUID, source_text: str, *,
                      source: str = "chat") -> dict:
    """Intelligently extract personal memories and merge them with existing ones (Mem0-style ADD/UPDATE/dedup/conflict resolution). Returns {added, updated}."""
    txt = (source_text or "").strip()
    if not txt:
        return {"added": 0, "updated": 0}
    existing = await recall(db, user_id, txt[:600], limit=8)
    ex = "\n".join(f'- id={e["id"]}: {e["content"]}' for e in existing) or "(暂无)"
    prompt = _CONSOLIDATE_PROMPT + f"【已有记忆】\n{ex}\n\n【新内容】\n{txt[:4000]}"
    try:
        raw = await model_client.chat_complete(
            db, [{"role": "user", "content": prompt}], temperature=0.0, max_tokens=900)
    except ModelError as e:
        log.warning("memory_consolidate_failed", error=str(e))
        return {"added": 0, "updated": 0}
    valid = {e["id"] for e in existing}
    added = updated = 0
    for op in _parse_ops(raw):
        act = str(op.get("op", "")).upper()
        content = (op.get("content") or "").strip()
        kind = op.get("kind", "fact")
        if act == "ADD" and content:
            await remember(db, user_id, content, kind=kind, source=source)
            added += 1
        elif act == "UPDATE" and content and str(op.get("id")) in valid:
            await _update_memory(db, str(op["id"]), content, kind)
            updated += 1
    return {"added": added, "updated": updated}


async def extract(db: AsyncSession, user_id: uuid.UUID, source_text: str) -> int:
    """User-initiated memory extraction from a block of text (/memories/extract). Runs intelligent merge; returns count of added + updated."""
    r = await consolidate(db, user_id, source_text, source="manual")
    return r["added"] + r["updated"]


# ---- Auto-memory toggle (per-user, on by default) + background fire-and-forget merge ----

_MEM_PREF_KEY = "memory_prefs"


async def auto_enabled(db: AsyncSession, user_id: uuid.UUID) -> bool:
    from app.services.platform_settings import get_setting
    s = await get_setting(db, _MEM_PREF_KEY, scope="user", scope_id=str(user_id))
    return bool((s or {}).get("auto", True))


async def set_auto(db: AsyncSession, user_id: uuid.UUID, enabled: bool) -> None:
    from sqlalchemy import select as _select

    from app.models.system_setting import SystemSetting
    row = (await db.execute(_select(SystemSetting).where(
        SystemSetting.key == _MEM_PREF_KEY, SystemSetting.scope == "user",
        SystemSetting.scope_id == str(user_id)))).scalar_one_or_none()
    if row is None:
        db.add(SystemSetting(id=uuid.uuid4(), key=_MEM_PREF_KEY, scope="user",
                             scope_id=str(user_id), value={"auto": bool(enabled)}))
    else:
        row.value = {"auto": bool(enabled)}
    await db.commit()


async def consolidate_bg(user_id: uuid.UUID, source_text: str, source: str) -> None:
    """Background fire-and-forget: opens its own session, respects the auto toggle, logs on failure only. Called from chat/upload."""
    from app.db.session import get_sessionmaker
    try:
        async with get_sessionmaker()() as db:
            if not await auto_enabled(db, user_id):
                return
            r = await consolidate(db, user_id, source_text, source=source)
            if r["added"] or r["updated"]:
                log.info("memory_auto", source=source, added=r["added"], updated=r["updated"])
    except Exception as e:  # noqa: BLE001
        log.warning("memory_auto_bg_failed", source=source, error=str(e))

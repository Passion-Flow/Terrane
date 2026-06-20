"""个人 AI 助手（前台 /api/v1/assistant）—— Kimi 式:跨「用户全部知识库」自动检索 + 记忆唤回
   + 持久化对话历史。可问任何问题,知识库/记忆相关时优先采用并标引用。SSE 流式。
"""

from __future__ import annotations

import asyncio
import base64
import json as _json
import os
import tempfile
import uuid

import structlog
from fastapi import APIRouter, Depends, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db_session
from app.core.errors import BizError
from app.db.session import get_sessionmaker
from app.models.conversation import Conversation, Message
from app.models.knowledge_base import KbMember, KnowledgeBase
from app.services import memory_service, model_client
from app.services.model_client import ModelError, chat_stream, chat_stream_search
from app.services.model_channels import get_channel, get_channel_by_model
from app.services.parse import engine as parse_engine
from app.services.parse import video as video_parser

log = structlog.get_logger("terrane.assistant")
router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

_SYSTEM = (
    "你是 Terrane,用户专属的 AI 助手。你可以回答任何问题。当下面提供了【知识库资料】或【个人记忆】且与问题相关时,"
    "优先采用它们,并在引用知识库内容的句子末尾用 [1][2] 标注来源编号;资料不足或无关时,用你的通用知识自然作答。"
    "回答简洁、准确、友好,用与提问相同的语言。"
)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"


async def _parse_attachment(db: AsyncSession, att: dict) -> str:
    """聊天附件 → 文本上下文:图片→VL、音频→ASR、视频→抽帧+ASR、文档→解析引擎、文本→直读。"""
    from fastapi.concurrency import run_in_threadpool
    name = att.get("name", "file")
    mime = att.get("mime", "") or ""
    data_url = att.get("data", "") or ""
    b64 = data_url.split(",", 1)[-1] if "," in data_url else data_url
    try:
        raw = base64.b64decode(b64)
    except Exception:  # noqa: BLE001
        return ""
    try:
        if mime.startswith("image/"):
            cap = await model_client.vl_caption(db, b64)
            return f"图片「{name}」内容:{cap}" if cap else ""
        if mime.startswith("audio/"):
            tr = await model_client.asr(db, b64, mime=mime or "audio/wav")
            return f"音频「{name}」转录:{tr}" if tr else ""
        ext = os.path.splitext(name)[1]
        if mime in video_parser.VIDEO_MIMES or mime.startswith("video/"):
            with tempfile.NamedTemporaryFile(suffix=ext or ".mp4", delete=False) as tf:
                tf.write(raw); tmp = tf.name
            try:
                txt = await video_parser.parse_video(db, tmp)
                return f"视频「{name}」:\n{txt}" if txt else ""
            finally:
                os.unlink(tmp)
        if mime in parse_engine.SUPPORTED:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
                tf.write(raw); tmp = tf.name
            try:
                txt = await run_in_threadpool(parse_engine.parse, tmp, mime)
                return f"文档「{name}」:\n{txt}" if txt else ""
            finally:
                os.unlink(tmp)
        return f"文件「{name}」:\n" + raw.decode("utf-8")
    except (ModelError, UnicodeDecodeError, Exception):  # noqa: BLE001
        return ""


async def _accessible_kb_ids(db: AsyncSession, user: CurrentUser) -> list[uuid.UUID]:
    uid = uuid.UUID(user.user_id)
    member = select(KbMember.kb_id).where(KbMember.user_id == uid)
    rows = (await db.execute(select(KnowledgeBase.id).where(or_(
        KnowledgeBase.owner_id == uid,
        (KnowledgeBase.workspace_id == uuid.UUID(user.workspace_id)) & (KnowledgeBase.visibility == "workspace"),
        KnowledgeBase.id.in_(member),
    )))).scalars().all()
    return list(rows)


async def _search_all(db: AsyncSession, kb_ids: list[uuid.UUID], query: str, limit: int,
                      embed_model: str | None, rerank_model: str | None) -> list[dict]:
    """跨用户全部知识库的混合检索(嵌入一次 + 向量/词法 across kb_ids + rerank)。"""
    if not kb_ids or not query.strip():
        return []
    ids = [str(i) for i in kb_ids]
    cand: dict[str, dict] = {}
    lex = (await db.execute(text("""
        SELECT c.id, c.content, r.title src, k.name kb FROM chunks c
        JOIN raw_sources r ON r.id=c.raw_source_id JOIN knowledge_bases k ON k.id=c.kb_id
        WHERE c.kb_id = ANY(:ids) AND (c.content ILIKE :like OR similarity(c.content,:q)>0.05)
        ORDER BY similarity(c.content,:q) DESC LIMIT 20
    """), {"ids": ids, "q": query, "like": f"%{query}%"})).mappings().all()
    for r in lex:
        cand[str(r["id"])] = {"content": r["content"], "source_title": r["src"], "kb": r["kb"]}
    try:
        qv = await model_client.embed_query(db, query, model=embed_model)
    except ModelError:
        qv = None
    if qv:
        vlit = "[" + ",".join(f"{x:.6f}" for x in qv) + "]"
        vrows = (await db.execute(text("""
            SELECT c.id, c.content, r.title src, k.name kb FROM chunks c
            JOIN raw_sources r ON r.id=c.raw_source_id JOIN knowledge_bases k ON k.id=c.kb_id
            WHERE c.kb_id = ANY(:ids) AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> (:v)::halfvec LIMIT 20
        """), {"ids": ids, "v": vlit})).mappings().all()
        for r in vrows:
            cand.setdefault(str(r["id"]), {"content": r["content"], "source_title": r["src"], "kb": r["kb"]})
    items = list(cand.values())
    if not items:
        return []
    try:
        rr = await model_client.rerank(db, query, [c["content"] for c in items], top_n=limit, model=rerank_model)
    except ModelError:
        rr = None
    ordered = ([items[i] for i, _ in rr if i < len(items)] if rr else items)[:limit]
    return ordered


# ---- 对话 CRUD ----

@router.get("/conversations")
async def list_conversations(user: CurrentUser = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db_session)) -> dict:
    rows = (await db.execute(select(Conversation).where(Conversation.user_id == uuid.UUID(user.user_id))
                             .order_by(Conversation.updated_at.desc()).limit(100))).scalars().all()
    return {"items": [{"id": str(c.id), "title": c.title, "updated_at": c.updated_at.isoformat() if c.updated_at else None} for c in rows]}


@router.get("/conversations/{cid}")
async def get_conversation(cid: str = Path(...), user: CurrentUser = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db_session)) -> dict:
    conv = await _load_conv(db, cid, user)
    msgs = (await db.execute(select(Message).where(Message.conversation_id == conv.id)
                             .order_by(Message.created_at.asc()))).scalars().all()
    return {"id": str(conv.id), "title": conv.title,
            "messages": [{"role": m.role, "content": m.content,
                          "sources": m.meta.get("sources", []),
                          "web_sources": m.meta.get("web_sources", []),
                          "attachments": m.meta.get("attachments", [])} for m in msgs]}


@router.delete("/conversations/{cid}")
async def delete_conversation(cid: str = Path(...), user: CurrentUser = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db_session)) -> dict:
    conv = await _load_conv(db, cid, user)
    await db.delete(conv)
    await db.commit()
    return {"ok": True}


async def _load_conv(db: AsyncSession, cid: str, user: CurrentUser) -> Conversation:
    try:
        c = await db.get(Conversation, uuid.UUID(cid))
    except ValueError:
        c = None
    if c is None or str(c.user_id) != user.user_id:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "conversation"})
    return c


# ---- 助手对话(SSE)----

class AssistChatIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    query: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    model: str | None = Field(default=None, max_length=128)
    embed_model: str | None = Field(default=None, max_length=128)
    rerank_model: str | None = Field(default=None, max_length=128)
    attachments: list[dict] = Field(default_factory=list)  # [{name, mime, data(base64)}]
    att_meta: list[dict] = Field(default_factory=list)      # 气泡缩略图元信息 [{name, mime, thumb}]
    use_kb: bool = False                                    # 知识库开关(默认关=普通问答)
    kb_ids: list[str] = Field(default_factory=list)         # 指定库(空=全部可见库)
    web_search: bool = False                                # 联网搜索开关(默认关)


@router.post("/chat")
async def assistant_chat(body: AssistChatIn, user: CurrentUser = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db_session)) -> StreamingResponse:
    uid = uuid.UUID(user.user_id)
    # 对话:加载或新建
    if body.conversation_id:
        conv = await _load_conv(db, body.conversation_id, user)
    else:
        conv = Conversation(id=uuid.uuid4(), user_id=uid, title=body.query[:40])
        db.add(conv)
        await db.flush()
    # 历史(最近 8 条)
    hist = (await db.execute(select(Message).where(Message.conversation_id == conv.id)
                             .order_by(Message.created_at.desc()).limit(8))).scalars().all()
    history = [{"role": m.role, "content": m.content} for m in reversed(hist)]
    # 存用户消息(附件缩略图元信息进 meta,供气泡 + 重载显示)
    db.add(Message(id=uuid.uuid4(), conversation_id=conv.id, role="user", content=body.query,
                   meta={"attachments": body.att_meta[:8]} if body.att_meta else {}))
    # 知识库检索(仅当开启;可指定库,否则全部可见库)
    hits: list[dict] = []
    if body.use_kb:
        accessible = await _accessible_kb_ids(db, user)
        if body.kb_ids:
            sel = set()
            for k in body.kb_ids:
                try:
                    sel.add(uuid.UUID(k))
                except ValueError:
                    pass
            use_ids = [k for k in accessible if k in sel]
        else:
            use_ids = accessible
        hits = await _search_all(db, use_ids, body.query, 6, body.embed_model, body.rerank_model)
    try:
        mems = await memory_service.recall(db, uid, body.query, limit=3)
    except Exception:  # noqa: BLE001
        mems = []
    # 聊天附件(文档/图片/视频/音频)→ 解析进上下文
    att_texts: list[str] = []
    for att in (body.attachments or [])[:5]:
        txt = await _parse_attachment(db, att)
        if txt:
            att_texts.append(txt[:8000])
    ch = (await get_channel_by_model(db, "chat", body.model)) if body.model else None
    if ch is None:
        ch = await get_channel(db, "chat")
    conv_id = str(conv.id)
    await db.commit()

    if ch is None or not ch.base_url or not ch.api_key:
        async def no_model():
            yield _sse("meta", {"conversation_id": conv_id})
            yield _sse("error", {"code": "NO_CHAT_CHANNEL"})
            yield _sse("done", {})
        return StreamingResponse(no_model(), media_type="text/event-stream")

    base, key, model = ch.base_url, ch.api_key, ch.model or "qwen-plus"
    src = [{"n": i + 1, "source_title": h["source_title"], "kb": h.get("kb", ""), "content": h["content"]} for i, h in enumerate(hits)]
    ctx_parts = []
    if hits:
        ctx_parts.append("【知识库资料】\n" + "\n\n".join(f"[{i + 1}] ({h.get('kb', '')}/{h['source_title']}) {h['content']}" for i, h in enumerate(hits)))
    if mems:
        ctx_parts.append("【个人记忆】\n" + "\n".join(f"- {m['content']}" for m in mems))
    if att_texts:
        ctx_parts.append("【本次附件】\n" + "\n\n".join(att_texts))
    user_content = (("\n\n".join(ctx_parts) + "\n\n") if ctx_parts else "") + "【问题】" + body.query
    messages = [{"role": "system", "content": _SYSTEM}, *history, {"role": "user", "content": user_content}]

    use_native = body.web_search and "dashscope" in base.lower()

    async def gen():
        yield _sse("meta", {"conversation_id": conv_id})
        yield _sse("sources", {"hits": src})
        answer = ""
        web_sources: list[dict] = []
        streamed = False
        if use_native:  # 联网搜索:原生流式带来源卡片;配置模型不支持原生(如 qwen3.7-plus)则回退 qwen-plus
            candidates = [model, "qwen-plus"] if model != "qwen-plus" else ["qwen-plus"]
            for try_model in candidates:
                got = False
                try:
                    async for kind_, payload in chat_stream_search(key, try_model, messages):
                        got = True
                        streamed = True
                        if kind_ == "sources":
                            web_sources = payload
                            yield _sse("web_sources", {"results": payload})
                        else:
                            answer += payload
                            yield _sse("delta", {"text": payload})
                except ModelError:
                    got = False
                if got:
                    break
        if not streamed:  # 普通对话 或 原生不可用 → compatible-mode(web_search 时仍内置联网,无卡片)
            try:
                async for delta in chat_stream(base, key, model, messages, enable_search=body.web_search):
                    answer += delta
                    yield _sse("delta", {"text": delta})
            except ModelError as e:
                yield _sse("error", {"message": str(e)})
        # 流后持久化助手消息(新 session,请求 session 已关)
        try:
            meta: dict = {"sources": src}
            if web_sources:
                meta["web_sources"] = web_sources
            async with get_sessionmaker()() as s2:
                s2.add(Message(id=uuid.uuid4(), conversation_id=uuid.UUID(conv_id), role="assistant",
                               content=answer, meta=meta))
                await s2.execute(text("UPDATE conversations SET updated_at=now() WHERE id=:c"), {"c": conv_id})
                await s2.commit()
        except Exception as e:  # noqa: BLE001
            log.warning("assistant_persist_failed", error=str(e))
        # 自动记忆:后台从本轮对话抽取个人记忆(尊重用户开关,不阻塞响应)
        if answer.strip():
            asyncio.create_task(memory_service.consolidate_bg(
                uid, f"用户: {body.query}\n助手: {answer}", "chat"))
        yield _sse("done", {})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

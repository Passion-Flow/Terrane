"""知识库 API（前台 /api/v1/knowledge-bases，平台库 terrane_main）。

库 = 知识复利的容器(Raw 源 → 编译 → Wiki + 图)。本端点先做库本体 CRUD + 可见性/库角色 ACL;
摄入/检索/图在后续端点。可见性:private(owner+显式成员)/ shared(显式成员)/ workspace(本工作区可见)。
ACL:owner 全权;kb editor 可改;owner 才可删;有 access 才可读。License 锁定态被中间件拦。
"""

from __future__ import annotations

import asyncio
import re
import secrets
import uuid
from typing import Literal

import hashlib
import json as _json
import secrets

import os
import tempfile

import structlog
from fastapi import APIRouter, Depends, File, Path, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db_session
from app.core.errors import BizError
from app.models.api_key import ApiKey
from app.models.kb_content import Chunk, RawSource
from app.models.knowledge_base import VISIBILITY, KbMember, KnowledgeBase
from app.models.user import User
from app.services import graph_service, ingest_service, memory_service, studio_service, wiki_service
from app.services.parse import engine as parse_engine
from app.services.parse import video as video_parser
from app.services.model_channels import get_channel, get_channel_by_model
from app.services.model_client import ModelError, chat_stream

log = structlog.get_logger("terrane.kb")

router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["knowledge-bases"])


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "kb"
    return f"{base}-{secrets.token_hex(3)}"


def _kid(kb_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(kb_id)
    except ValueError:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "knowledge_base"})


async def _my_role(db: AsyncSession, kb: KnowledgeBase, user: CurrentUser) -> str | None:
    """返回 user 对 kb 的有效角色:owner / editor / viewer / None(无访问)。"""
    if str(kb.owner_id) == user.user_id:
        return "owner"
    m = (await db.execute(select(KbMember).where(
        KbMember.kb_id == kb.id, KbMember.user_id == uuid.UUID(user.user_id)))).scalar_one_or_none()
    if m is not None:
        return m.role
    if kb.visibility == "workspace" and str(kb.workspace_id) == user.workspace_id:
        return "viewer"
    return None


def _out(kb: KnowledgeBase, my_role: str | None) -> dict:
    return {
        "id": str(kb.id), "workspace_id": str(kb.workspace_id),
        "owner_id": str(kb.owner_id) if kb.owner_id else None,
        "name": kb.name, "slug": kb.slug, "description": kb.description,
        "visibility": kb.visibility, "status": kb.status,
        "my_role": my_role, "is_owner": my_role == "owner",
        "created_at": kb.created_at.isoformat() if kb.created_at else None,
    }


class CreateKbIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    visibility: Literal["private", "shared", "workspace"] = "private"


@router.get("")
async def list_kbs(user: CurrentUser = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db_session)) -> dict:
    """当前用户可见的库:自己拥有的 + 本工作区 workspace 可见的 + 被显式共享(kb_member)的。"""
    uid = uuid.UUID(user.user_id)
    member_kb_ids = select(KbMember.kb_id).where(KbMember.user_id == uid)
    stmt = (select(KnowledgeBase).where(or_(
        KnowledgeBase.owner_id == uid,
        (KnowledgeBase.workspace_id == uuid.UUID(user.workspace_id)) & (KnowledgeBase.visibility == "workspace"),
        KnowledgeBase.id.in_(member_kb_ids),
    )).order_by(KnowledgeBase.created_at.desc()))
    rows = (await db.execute(stmt)).scalars().all()
    items = [_out(kb, await _my_role(db, kb, user)) for kb in rows]
    return {"items": items, "total": len(items)}


@router.post("", status_code=201)
async def create_kb(body: CreateKbIn, user: CurrentUser = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db_session)) -> dict:
    if body.visibility not in VISIBILITY:
        raise BizError("VALIDATION_FAILED", {"reason": "visibility"})
    kb = KnowledgeBase(
        workspace_id=uuid.UUID(user.workspace_id), owner_id=uuid.UUID(user.user_id),
        slug=_slug(body.name), name=body.name, description=body.description,
        visibility=body.visibility, status="active")
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    log.info("kb_created", kb_id=str(kb.id), user_id=user.user_id)
    return _out(kb, "owner")


async def _load(db: AsyncSession, kb_id: str, user: CurrentUser) -> tuple[KnowledgeBase, str]:
    kb = await db.get(KnowledgeBase, _kid(kb_id))
    if kb is None:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "knowledge_base"})
    role = await _my_role(db, kb, user)
    if role is None:
        raise BizError("PERM_DENIED", {"resource": "knowledge_base"})
    return kb, role


@router.get("/{kb_id}")
async def get_kb(kb_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, role = await _load(db, kb_id, user)
    return _out(kb, role)


class UpdateKbIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    visibility: Literal["private", "shared", "workspace"] | None = None


@router.patch("/{kb_id}")
async def update_kb(body: UpdateKbIn, kb_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, role = await _load(db, kb_id, user)
    if role not in ("owner", "editor"):
        raise BizError("PERM_DENIED", {"need": "editor"})
    if body.name is not None:
        kb.name = body.name
    if body.description is not None:
        kb.description = body.description or None
    if body.visibility is not None:
        kb.visibility = body.visibility
    await db.commit()
    return _out(kb, role)


@router.delete("/{kb_id}")
async def delete_kb(kb_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, role = await _load(db, kb_id, user)
    if role != "owner":
        raise BizError("PERM_DENIED", {"need": "owner"})
    await db.delete(kb)   # 硬删 + 级联(kb_members/raw_sources/chunks/wiki/jobs)
    await db.commit()
    log.info("kb_deleted", kb_id=kb_id, user_id=user.user_id)
    return {"ok": True}


# ---- 库共享（kb_members：owner 邀请同工作区用户为 viewer/editor）----

@router.get("/{kb_id}/members")
async def list_members(kb_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, _ = await _load(db, kb_id, user)
    rows = (await db.execute(
        select(KbMember, User).join(User, User.id == KbMember.user_id)
        .where(KbMember.kb_id == kb.id))).all()
    members = [{"user_id": str(u.id), "email": u.email, "username": u.username, "role": m.role}
               for m, u in rows]
    owner = None
    if kb.owner_id:
        ow = await db.get(User, kb.owner_id)
        if ow:
            owner = {"user_id": str(ow.id), "email": ow.email, "username": ow.username, "role": "owner"}
    return {"owner": owner, "members": members}


class AddMemberIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    role: Literal["viewer", "editor"] = "viewer"


@router.post("/{kb_id}/members", status_code=201)
async def add_member(body: AddMemberIn, kb_id: str = Path(...),
                     user: CurrentUser = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, role = await _load(db, kb_id, user)
    if role != "owner":
        raise BizError("PERM_DENIED", {"need": "owner"})
    target = (await db.execute(select(User).where(
        func.lower(User.email) == body.email.lower(),
        User.workspace_id == kb.workspace_id))).scalar_one_or_none()
    if target is None:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "user"})
    if str(target.id) == str(kb.owner_id):
        raise BizError("VALIDATION_FAILED", {"reason": "owner_is_member"})
    existing = (await db.execute(select(KbMember).where(
        KbMember.kb_id == kb.id, KbMember.user_id == target.id))).scalar_one_or_none()
    if existing is not None:
        existing.role = body.role
    else:
        db.add(KbMember(kb_id=kb.id, user_id=target.id, role=body.role))
    await db.commit()
    log.info("kb_member_added", kb_id=kb_id, target=str(target.id), role=body.role)
    return {"user_id": str(target.id), "email": target.email, "username": target.username, "role": body.role}


@router.delete("/{kb_id}/members/{member_user_id}")
async def remove_member(kb_id: str = Path(...), member_user_id: str = Path(...),
                        user: CurrentUser = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, role = await _load(db, kb_id, user)
    if role != "owner":
        raise BizError("PERM_DENIED", {"need": "owner"})
    try:
        muid = uuid.UUID(member_user_id)
    except ValueError:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "member"})
    m = (await db.execute(select(KbMember).where(
        KbMember.kb_id == kb.id, KbMember.user_id == muid))).scalar_one_or_none()
    if m is None:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "member"})
    await db.delete(m)
    await db.commit()
    return {"ok": True}


# ---- 源摄入 + 检索（知识复利第一段:文本入库 → 切片 → 词法检索）----

class AddSourceIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    title: str = Field(min_length=1, max_length=512)
    text: str = Field(min_length=1, max_length=2_000_000)
    kind: Literal["text", "url"] = "text"


@router.post("/{kb_id}/sources", status_code=201)
async def add_source(body: AddSourceIn, kb_id: str = Path(...),
                     user: CurrentUser = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, role = await _load(db, kb_id, user)
    if role not in ("owner", "editor"):
        raise BizError("PERM_DENIED", {"need": "editor"})
    raw, n = await ingest_service.add_text_source(
        db, kb_id=kb.id, workspace_id=kb.workspace_id, title=body.title, body=body.text, kind=body.kind)
    asyncio.create_task(memory_service.consolidate_bg(uuid.UUID(user.user_id), body.text, "document"))
    return {"id": str(raw.id), "title": raw.title, "status": raw.status, "chunk_count": n}


_EXT_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".avi": "video/x-msvideo",
    ".webm": "video/webm", ".mkv": "video/x-matroska",
}


@router.post("/{kb_id}/sources/upload", status_code=201)
async def upload_source(kb_id: str = Path(...), file: UploadFile = File(...),
                        user: CurrentUser = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db_session)) -> dict:
    """上传文件 → Terrane Parse 解析(PDF/Office,CPU)或文本直读 → 切片/嵌入摄入。"""
    kb, role = await _load(db, kb_id, user)
    if role not in ("owner", "editor"):
        raise BizError("PERM_DENIED", {"need": "editor"})
    data = await file.read()
    fname = file.filename or "upload"
    ext = os.path.splitext(fname)[1].lower()
    mime = _EXT_MIME.get(ext, file.content_type or "")
    cap = 300_000_000 if mime in video_parser.VIDEO_MIMES else 30_000_000  # 视频放宽
    if len(data) > cap:
        raise BizError("VALIDATION_FAILED", {"reason": "file_too_large"})

    if mime in video_parser.VIDEO_MIMES:
        with tempfile.NamedTemporaryFile(suffix=ext or ".mp4", delete=False) as tf:
            tf.write(data)
            tmp = tf.name
        try:
            text = await video_parser.parse_video(db, tmp)   # ffmpeg 抽帧/音轨 → VL+ASR
        except Exception as e:  # noqa: BLE001
            log.warning("video_parse_failed", file=fname, error=str(e))
            text = None
        finally:
            os.unlink(tmp)
        if not text or not text.strip():
            return {"ok": False, "reason": "video_parse_empty"}
    elif mime in parse_engine.SUPPORTED:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
            tf.write(data)
            tmp = tf.name
        try:
            text = await run_in_threadpool(parse_engine.parse, tmp, mime)  # CPU 解析,丢线程池不堵事件循环
        except Exception as e:  # noqa: BLE001
            log.warning("parse_failed", file=fname, error=str(e))
            text = None
        finally:
            os.unlink(tmp)
        if not text or not text.strip():
            return {"ok": False, "reason": "parse_failed_or_empty"}
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise BizError("VALIDATION_FAILED", {"reason": "unsupported_file_type"})
        if not text.strip():
            return {"ok": False, "reason": "empty"}

    raw, n = await ingest_service.add_text_source(
        db, kb_id=kb.id, workspace_id=kb.workspace_id, title=fname, body=text, kind="file")
    asyncio.create_task(memory_service.consolidate_bg(uuid.UUID(user.user_id), text, "document"))
    return {"id": str(raw.id), "title": raw.title, "status": raw.status, "chunk_count": n}


@router.get("/{kb_id}/sources")
async def list_sources(kb_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, _ = await _load(db, kb_id, user)
    rows = (await db.execute(select(RawSource).where(RawSource.kb_id == kb.id)
                             .order_by(RawSource.created_at.desc()))).scalars().all()
    counts = dict((await db.execute(select(Chunk.raw_source_id, func.count())
                                    .where(Chunk.kb_id == kb.id).group_by(Chunk.raw_source_id))).all())
    return {"items": [{
        "id": str(r.id), "title": r.title, "kind": r.kind, "status": r.status,
        "size_bytes": r.size_bytes, "chunk_count": int(counts.get(r.id, 0)),
        "error": r.error, "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}


@router.delete("/{kb_id}/sources/{source_id}")
async def delete_source(kb_id: str = Path(...), source_id: str = Path(...),
                        user: CurrentUser = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, role = await _load(db, kb_id, user)
    if role not in ("owner", "editor"):
        raise BizError("PERM_DENIED", {"need": "editor"})
    try:
        sid = uuid.UUID(source_id)
    except ValueError:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "source"})
    raw = await db.get(RawSource, sid)
    if raw is None or raw.kb_id != kb.id:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "source"})
    await db.delete(raw)   # 硬删 + 级联(chunks ON DELETE CASCADE)
    await db.commit()
    log.info("source_deleted", kb_id=kb_id, source_id=source_id, user_id=user.user_id)
    return {"ok": True}


@router.get("/{kb_id}/search")
async def search_kb(kb_id: str = Path(...), q: str = "", limit: int = 10,
                    embed_model: str = "", rerank_model: str = "",
                    user: CurrentUser = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, _ = await _load(db, kb_id, user)
    hits = await ingest_service.search_chunks(db, kb_id=kb.id, query=q, limit=min(max(limit, 1), 50),
                                              embed_model=embed_model or None, rerank_model=rerank_model or None)
    return {"query": q, "hits": hits, "total": len(hits)}


@router.post("/{kb_id}/graph/build")
async def build_graph(kb_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db_session)) -> dict:
    """从库内各源抽取实体/关系,构建知识图谱(AGE)。需 editor/owner。LLM 抽取,可能较慢。"""
    kb, role = await _load(db, kb_id, user)
    if role not in ("owner", "editor"):
        raise BizError("PERM_DENIED", {"need": "editor"})
    rows = (await db.execute(select(RawSource.title, RawSource.parsed_text)
                             .where(RawSource.kb_id == kb.id, RawSource.parsed_text.is_not(None)))).all()
    sources = [(t, x) for t, x in rows]
    if not sources:
        return {"entities_added": 0, "relations_added": 0}
    result = await graph_service.build_graph(db, kb.id, sources)
    return result


@router.get("/{kb_id}/graph")
async def get_graph(kb_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, _ = await _load(db, kb_id, user)
    return await graph_service.graph_data(db, kb.id)


@router.post("/{kb_id}/studio/{kind}")
async def studio_generate(kb_id: str = Path(...), kind: str = Path(...),
                          user: CurrentUser = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db_session)) -> dict:
    """Studio 生成(NotebookLM 式):study_guide/faq/briefing/timeline/mind_map/flashcards/quiz/data_table。"""
    kb, _ = await _load(db, kb_id, user)
    if kind not in studio_service.KINDS:
        raise BizError("VALIDATION_FAILED", {"reason": "kind"})
    rows = (await db.execute(select(RawSource.title, RawSource.parsed_text)
                             .where(RawSource.kb_id == kb.id, RawSource.parsed_text.is_not(None)))).all()
    if not rows:
        return {"ok": False, "reason": "no_sources"}
    try:
        return await studio_service.generate(db, kind=kind, sources=[(t, x) for t, x in rows])
    except ModelError:
        return {"ok": False, "reason": "model_error"}


@router.post("/{kb_id}/audio-overview")
async def studio_audio_overview(kb_id: str = Path(...),
                                user: CurrentUser = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db_session)) -> dict:
    """Studio 媒体:双人播客音频(TTS),返回 {script, audio(data url)}。"""
    kb, _ = await _load(db, kb_id, user)
    rows = (await db.execute(select(RawSource.title, RawSource.parsed_text)
                             .where(RawSource.kb_id == kb.id, RawSource.parsed_text.is_not(None)))).all()
    if not rows:
        return {"ok": False, "reason": "no_sources"}
    try:
        return await studio_service.generate_podcast(db, sources=[(t, x) for t, x in rows])
    except ModelError as e:
        s = str(e)
        reason = "no_tts_channel" if "no_tts_channel" in s else ("rate_limited" if "429" in s else "model_error")
        return {"ok": False, "reason": reason}


@router.post("/{kb_id}/slide-deck/export")
async def studio_slide_export(kb_id: str = Path(...),
                              user: CurrentUser = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db_session)) -> StreamingResponse:
    """Studio 媒体:幻灯片导出为 .pptx 下载。"""
    import io

    kb, _ = await _load(db, kb_id, user)
    rows = (await db.execute(select(RawSource.title, RawSource.parsed_text)
                             .where(RawSource.kb_id == kb.id, RawSource.parsed_text.is_not(None)))).all()
    if not rows:
        raise BizError("VALIDATION_FAILED", {"reason": "no_sources"})
    res = await studio_service.generate(db, kind="slide_deck", sources=[(t, x) for t, x in rows])
    deck = res.get("content")
    if not deck:
        raise BizError("VALIDATION_FAILED", {"reason": "empty"})
    data = studio_service.build_pptx(deck)
    return StreamingResponse(io.BytesIO(data),
                             media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                             headers={"Content-Disposition": 'attachment; filename="terrane-slides.pptx"'})


@router.get("/{kb_id}/lint")
async def lint_kb(kb_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db_session)) -> dict:
    """Agent·Lint 体检:扫描库健康度(源/切片/嵌入/图谱/Wiki),给问题清单 + 评分。"""
    kb, _ = await _load(db, kb_id, user)
    n_src = int((await db.execute(select(func.count()).select_from(RawSource)
                                  .where(RawSource.kb_id == kb.id))).scalar_one())
    n_failed = int((await db.execute(select(func.count()).select_from(RawSource)
                                     .where(RawSource.kb_id == kb.id, RawSource.status == "failed"))).scalar_one())
    n_chunk = int((await db.execute(select(func.count()).select_from(Chunk)
                                    .where(Chunk.kb_id == kb.id))).scalar_one())
    n_embed = int((await db.execute(text(
        "SELECT count(*) FROM chunks WHERE kb_id = :k AND embedding IS NOT NULL"),
        {"k": str(kb.id)})).scalar_one())
    gdata = await graph_service.graph_data(db, kb.id, limit=1)
    has_graph = len(gdata["nodes"]) > 0
    wiki = await wiki_service.get_page(db, kb.id, "overview")

    issues: list[dict] = []
    if n_src == 0:
        issues.append({"level": "info", "code": "no_sources", "msg": "知识库还没有任何资料。"})
    if n_failed:
        issues.append({"level": "warn", "code": "failed_sources", "msg": f"{n_failed} 个源解析失败。"})
    if n_chunk and n_embed < n_chunk:
        issues.append({"level": "warn", "code": "unembedded", "msg": f"{n_chunk - n_embed}/{n_chunk} 切片未生成向量(嵌入渠道未配置或失败),向量检索不完整。"})
    if n_src and not has_graph:
        issues.append({"level": "info", "code": "no_graph", "msg": "尚未构建知识图谱,点「构建图谱」可生成。"})
    if n_src and wiki is None:
        issues.append({"level": "info", "code": "no_wiki", "msg": "尚未编译 Wiki,点「编译 Wiki」可生成。"})

    score = 100
    score -= 40 if n_failed else 0
    score -= 25 if (n_chunk and n_embed < n_chunk) else 0
    score -= 10 if (n_src and not has_graph) else 0
    score -= 10 if (n_src and wiki is None) else 0
    return {"score": max(score, 0),
            "stats": {"sources": n_src, "failed_sources": n_failed, "chunks": n_chunk,
                      "embedded_chunks": n_embed, "graph_nodes": len(gdata["nodes"]), "has_wiki": wiki is not None},
            "issues": issues}


def _wiki_out(p) -> dict:
    return {"id": str(p.id), "slug": p.slug, "title": p.title, "body_md": p.body_md,
            "source": p.source, "status": p.status, "inferred": p.inferred,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None}


@router.post("/{kb_id}/wiki/compile")
async def compile_wiki(kb_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db_session)) -> dict:
    """知识复利:把库内各源 LLM 编译成结构化 Wiki 概览页。需 editor/owner。"""
    kb, role = await _load(db, kb_id, user)
    if role not in ("owner", "editor"):
        raise BizError("PERM_DENIED", {"need": "editor"})
    rows = (await db.execute(select(RawSource.title, RawSource.parsed_text)
                             .where(RawSource.kb_id == kb.id, RawSource.parsed_text.is_not(None)))).all()
    try:
        page = await wiki_service.compile_overview(db, kb.id, kb.workspace_id, kb.name, [(t, x) for t, x in rows])
    except ModelError:
        return {"ok": False, "reason": "model_error"}
    if page is None:
        return {"ok": False, "reason": "no_sources"}
    return _wiki_out(page)


@router.get("/{kb_id}/wiki")
async def list_wiki(kb_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, _ = await _load(db, kb_id, user)
    pages = await wiki_service.list_pages(db, kb.id)
    return {"items": [{"id": str(p.id), "slug": p.slug, "title": p.title, "source": p.source,
                       "updated_at": p.updated_at.isoformat() if p.updated_at else None} for p in pages]}


@router.get("/{kb_id}/wiki/{slug}")
async def get_wiki(kb_id: str = Path(...), slug: str = Path(...),
                   user: CurrentUser = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, _ = await _load(db, kb_id, user)
    page = await wiki_service.get_page(db, kb.id, slug)
    if page is None:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "wiki_page"})
    return _wiki_out(page)


# ---- MCP 密钥（把库挂进 Claude/Cursor 的 Bearer 令牌,scope 到本库）----

class CreateKeyIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    name: str = Field(min_length=1, max_length=120)


@router.post("/{kb_id}/mcp-keys", status_code=201)
async def create_mcp_key(body: CreateKeyIn, kb_id: str = Path(...),
                         user: CurrentUser = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, role = await _load(db, kb_id, user)
    if role not in ("owner", "editor"):
        raise BizError("PERM_DENIED", {"need": "editor"})
    token = "trn_" + secrets.token_hex(24)
    k = ApiKey(id=uuid.uuid4(), user_id=uuid.UUID(user.user_id), kb_id=kb.id, name=body.name,
               token_prefix=token[:12], token_hash=hashlib.sha256(token.encode()).hexdigest())
    db.add(k)
    await db.commit()
    await db.refresh(k)
    # token 仅此一次返回
    return {"id": str(k.id), "name": k.name, "token": token, "token_prefix": k.token_prefix,
            "mcp_url": "/mcp", "created_at": k.created_at.isoformat() if k.created_at else None}


@router.get("/{kb_id}/mcp-keys")
async def list_mcp_keys(kb_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, _ = await _load(db, kb_id, user)
    rows = (await db.execute(select(ApiKey).where(ApiKey.kb_id == kb.id)
                             .order_by(ApiKey.created_at.desc()))).scalars().all()
    return {"items": [{"id": str(k.id), "name": k.name, "token_prefix": k.token_prefix,
                       "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                       "created_at": k.created_at.isoformat() if k.created_at else None} for k in rows]}


@router.delete("/{kb_id}/mcp-keys/{key_id}")
async def delete_mcp_key(kb_id: str = Path(...), key_id: str = Path(...),
                         user: CurrentUser = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, role = await _load(db, kb_id, user)
    if role not in ("owner", "editor"):
        raise BizError("PERM_DENIED", {"need": "editor"})
    try:
        kid = uuid.UUID(key_id)
    except ValueError:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "key"})
    k = await db.get(ApiKey, kid)
    if k is None or k.kb_id != kb.id:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "key"})
    await db.delete(k)
    await db.commit()
    return {"ok": True}


_RAG_SYSTEM = (
    "你是知识库问答助手。严格依据下面给定的【资料】回答问题,并在相关句子末尾用 [1][2] 这样的编号标注"
    "引用的资料来源。若【资料】不足以回答,直说「资料中未提及」,绝不编造。用与提问相同的语言回答,简洁准确。"
)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"


class ChatIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=12)
    model: str | None = Field(default=None, max_length=128)  # 前台「模型设置」选定的模型(可选)


@router.post("/{kb_id}/chat")
async def chat_kb(body: ChatIn, kb_id: str = Path(...),
                  user: CurrentUser = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db_session)) -> StreamingResponse:
    """RAG 引用问答(SSE)。先发 sources(检索到的带编号切片),再流式发答案 delta,最后 done。
    注:检索 + 取渠道在返回前完成(DB 会话此时存活);生成器内只用已取好的渠道字段调模型,不碰 DB。"""
    kb, _ = await _load(db, kb_id, user)
    hits = await ingest_service.search_chunks(db, kb_id=kb.id, query=body.query, limit=body.top_k)
    ch = (await get_channel_by_model(db, "chat", body.model)) if body.model else None
    if ch is None:
        ch = await get_channel(db, "chat")
    src = [{"n": i + 1, "source_title": h["source_title"], "source_id": h["source_id"],
            "content": h["content"], "score": h["score"]} for i, h in enumerate(hits)]

    if ch is None or not ch.base_url or not ch.api_key:
        async def no_model():
            yield _sse("sources", {"hits": src})
            yield _sse("error", {"code": "NO_CHAT_CHANNEL"})
            yield _sse("done", {})
        return StreamingResponse(no_model(), media_type="text/event-stream")

    base, key, model = ch.base_url, ch.api_key, ch.model or "qwen-plus"
    context = "\n\n".join(f"[{i + 1}] {h['content']}" for i, h in enumerate(hits)) or "(知识库中暂无相关资料)"
    messages = [{"role": "system", "content": _RAG_SYSTEM},
                {"role": "user", "content": f"【资料】\n{context}\n\n【问题】{body.query}"}]

    async def gen():
        yield _sse("sources", {"hits": src})
        try:
            async for delta in chat_stream(base, key, model, messages):
                yield _sse("delta", {"text": delta})
        except ModelError as e:
            yield _sse("error", {"message": str(e)})
        yield _sse("done", {})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

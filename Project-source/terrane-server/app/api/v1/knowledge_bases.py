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
from fastapi import APIRouter, Depends, File, Form, Path, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db_session
from app.core.errors import BizError
from app.models.api_key import ApiKey
from app.models.kb_content import Chunk, IngestJob, RawSource, RawSourceOriginal, RawSourceRender
from app.models.knowledge_base import VISIBILITY, KbMember, KnowledgeBase
from app.models.user import User
from app.services import (
    graph_service, ingest_service, memory_service, render_service, storage, studio_service, wiki_service,
)
from app.services.parse import engine as parse_engine
from app.services.parse import video as video_parser
from app.services.parse import vl as parse_vl
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
    try:
        await graph_service.drop_graph(db, kb.id)   # AGE 图独立于关系表,删库时一并清
        await db.commit()
    except Exception as e:  # noqa: BLE001
        log.warning("graph_drop_failed", kb_id=kb_id, error=str(e))
    # 清对象存储:库内所有源的原文 + 页面图(DB 行随级联硬删,但对象存储需显式清)
    sids = (await db.execute(select(RawSource.id).where(RawSource.kb_id == kb.id))).scalars().all()
    for s in sids:
        await storage.delete_source_objects(s)
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
                        tier: str = Form("standard"),
                        user: CurrentUser = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db_session)) -> dict:
    """上传文件 → Terrane Parse 解析 → 切片/嵌入摄入。
    tier 解析档位:fast=纯词法;standard=词法+VL(图片/扫描);high=整页 VL 版面解析(高保真表格/公式/版面)。"""
    if tier not in ("fast", "standard", "high"):
        tier = "standard"
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

    is_text = mime not in video_parser.VIDEO_MIMES and mime not in parse_engine.SUPPORTED
    if is_text:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise BizError("VALIDATION_FAILED", {"reason": "unsupported_file_type"})

    # 先建「解析中」源并落原文/渲染,立即返回;解析+摄入异步进行(高精档 VL 慢,上传不阻塞)。
    raw = await ingest_service.create_pending_source(
        db, kb_id=kb.id, workspace_id=kb.workspace_id, title=fname, mime=mime, size=len(data))
    if mime not in video_parser.VIDEO_MIMES:
        in_obj = False
        try:
            await storage.ensure_bucket()
            await storage.get_adapter().upload(storage.original_key(raw.id), data,
                                               content_type=mime or "application/octet-stream")
            in_obj = True
        except Exception as e:  # noqa: BLE001 —— 对象存储不可用 → 降级 DB
            log.warning("original_object_store_failed", file=fname, error=str(e))
        if in_obj or len(data) <= 50_000_000:
            db.add(RawSourceOriginal(raw_source_id=raw.id, mime=mime or "application/octet-stream",
                                     size=len(data), data=None if in_obj else data))
            do_render = in_obj and render_service.renderable(mime)
            if do_render:
                db.add(RawSourceRender(raw_source_id=raw.id, status="pending"))
            await db.commit()
            if do_render:
                asyncio.create_task(render_service.render_source_bg(raw.id, data, mime, ext))
    asyncio.create_task(_ingest_bg(raw.id, uuid.UUID(user.user_id), data, mime, ext, tier))
    return {"id": str(raw.id), "title": raw.title, "status": raw.status}


async def _parse_by_tier(db: AsyncSession, data: bytes, mime: str, ext: str, tier: str) -> str | None:
    """按档位解析文件 → Markdown 文本。None/空串 = 失败。"""
    if mime in video_parser.VIDEO_MIMES:
        with tempfile.NamedTemporaryFile(suffix=ext or ".mp4", delete=False) as tf:
            tf.write(data)
            tmp = tf.name
        try:
            return await video_parser.parse_video(db, tmp)
        except Exception as e:  # noqa: BLE001
            log.warning("video_parse_failed", error=str(e))
            return None
        finally:
            os.unlink(tmp)
    if mime in parse_engine.SUPPORTED:
        text = None
        if mime == "application/pdf" and tier == "high":  # 高精:整页 VL 版面解析
            try:
                text = await parse_vl.parse_pdf_fullvl(db, data)
            except Exception as e:  # noqa: BLE001
                log.warning("vl_fullparse_failed", error=str(e))
        if not text:  # fast/standard 或高精回退 → 词法
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
                tf.write(data)
                tmp = tf.name
            try:
                text = await run_in_threadpool(parse_engine.parse, tmp, mime)
            except Exception as e:  # noqa: BLE001
                log.warning("parse_failed", error=str(e))
                text = None
            finally:
                os.unlink(tmp)
            if text and mime == "application/pdf" and tier != "fast":  # 标准:+ VL 图片/扫描增强
                try:
                    text = await parse_vl.enhance_pdf(db, data, text)
                except Exception as e:  # noqa: BLE001
                    log.warning("vl_enhance_failed", error=str(e))
        return text
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


async def _ingest_bg(rid: uuid.UUID, user_id: uuid.UUID, data: bytes, mime: str, ext: str, tier: str) -> None:
    """后台:按 tier 解析 → 写入源 + 切片/嵌入;失败置 status=failed。自带 session。"""
    from app.db.session import get_sessionmaker
    sm = get_sessionmaker()
    try:
        async with sm() as db:
            raw = await db.get(RawSource, rid)
            if raw is None:
                return
            text = await _parse_by_tier(db, data, mime, ext, tier)
            if not text or not text.strip():
                raw.status, raw.error = "failed", "parse_empty"
                await db.commit()
                return
            await ingest_service.reingest(db, raw, text)
        asyncio.create_task(memory_service.consolidate_bg(user_id, text, "document"))
    except Exception as e:  # noqa: BLE001
        log.warning("ingest_bg_failed", rid=str(rid), error=str(e))
        try:
            async with sm() as db:
                raw = await db.get(RawSource, rid)
                if raw:
                    raw.status, raw.error = "failed", str(e)[:500]
                    await db.commit()
        except Exception:  # noqa: BLE001
            pass


@router.post("/{kb_id}/sources/{source_id}/reparse")
async def reparse_source(kb_id: str = Path(...), source_id: str = Path(...), tier: str = Form("standard"),
                         user: CurrentUser = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db_session)) -> dict:
    """重新解析(换档 / 失败重试):取原文 → 后台按 tier 重解析 + 重摄入。需 editor/owner。"""
    if tier not in ("fast", "standard", "high"):
        tier = "standard"
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
    o = await db.get(RawSourceOriginal, sid)
    if o is None:
        raise BizError("VALIDATION_FAILED", {"reason": "no_original"})  # 无原文(如粘贴文本)不可重解析
    data = o.data
    if data is None:
        try:
            data = await storage.get_adapter().download(storage.original_key(sid))
        except Exception:  # noqa: BLE001
            raise BizError("RESOURCE_NOT_FOUND", {"resource": "original"})
    raw.status, raw.error = "parsing", None
    await db.commit()
    o_mime = o.mime or raw.mime or ""
    o_ext = os.path.splitext(raw.title)[1].lower()
    asyncio.create_task(_ingest_bg(sid, uuid.UUID(user.user_id), data, o_mime, o_ext, tier))
    return {"id": str(sid), "status": "parsing"}


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


@router.get("/{kb_id}/sources/{source_id}")
async def get_source(kb_id: str = Path(...), source_id: str = Path(...),
                     user: CurrentUser = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db_session)) -> dict:
    """取单个源的解析内容(预览)。返回 Terrane Parse 解析后的文本 + 元信息 + 切片数。"""
    kb, _ = await _load(db, kb_id, user)
    try:
        sid = uuid.UUID(source_id)
    except ValueError:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "source"})
    r = await db.get(RawSource, sid)
    if r is None or r.kb_id != kb.id:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "source"})
    n = int((await db.execute(select(func.count()).select_from(Chunk)
                              .where(Chunk.raw_source_id == r.id))).scalar_one())
    # 原文件的真实 mime(RawSource.mime 摄入时统一写 text/plain,左侧渲染要用原文件真 mime)
    orig_mime = (await db.execute(select(RawSourceOriginal.mime)
                                  .where(RawSourceOriginal.raw_source_id == r.id))).scalar_one_or_none()
    rnd = await db.get(RawSourceRender, r.id)
    return {"id": str(r.id), "title": r.title, "kind": r.kind, "mime": orig_mime or r.mime,
            "status": r.status, "size_bytes": r.size_bytes, "chunk_count": n,
            "error": r.error, "parsed_text": r.parsed_text or "", "has_original": orig_mime is not None,
            "render_status": rnd.status if rnd else None, "page_count": rnd.page_count if rnd else 0,
            "created_at": r.created_at.isoformat() if r.created_at else None}


@router.get("/{kb_id}/sources/{source_id}/pages")
async def get_source_pages(kb_id: str = Path(...), source_id: str = Path(...),
                           user: CurrentUser = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db_session)) -> dict:
    """取原文逐页 WebP 版面图的元信息(页数 + 每页尺寸)。前端据此占位 + 按视口懒加载单页。"""
    kb, _ = await _load(db, kb_id, user)
    try:
        sid = uuid.UUID(source_id)
    except ValueError:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "source"})
    r = await db.get(RawSource, sid)
    if r is None or r.kb_id != kb.id:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "source"})
    rnd = await db.get(RawSourceRender, sid)
    if rnd is None:
        return {"status": "none", "page_count": 0, "pages": []}
    return {"status": rnd.status, "page_count": rnd.page_count, "pages": rnd.pages}


@router.get("/{kb_id}/sources/{source_id}/page/{page_no}")
async def get_source_page(kb_id: str = Path(...), source_id: str = Path(...), page_no: int = Path(..., ge=1),
                          user: CurrentUser = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db_session)) -> StreamingResponse:
    """取单页 WebP 版面图(对象存储)。强缓存:页面图内容不可变。"""
    import io

    kb, _ = await _load(db, kb_id, user)
    try:
        sid = uuid.UUID(source_id)
    except ValueError:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "source"})
    r = await db.get(RawSource, sid)
    if r is None or r.kb_id != kb.id:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "source"})
    try:
        data = await storage.get_adapter().download(storage.page_key(sid, page_no))
    except Exception:  # noqa: BLE001 —— 该页尚未渲染 → 大文档按需即时渲染(仅 PDF)
        data = await _ondemand_page(db, sid, page_no)
        if data is None:
            raise BizError("RESOURCE_NOT_FOUND", {"resource": "page"})
    return StreamingResponse(io.BytesIO(data), media_type="image/webp",
                             headers={"Content-Disposition": "inline", "Cache-Control": "public, max-age=31536000, immutable"})


async def _ondemand_page(db: AsyncSession, sid: uuid.UUID, page_no: int) -> bytes | None:
    """按需渲染单页(滚到尚未渐进渲染到的页):取原文 PDF → 渲该页 → 存回 → 返回字节。
    仅 PDF（Office 依赖后台渐进渲染，单页再转换代价高）。"""
    o = await db.get(RawSourceOriginal, sid)
    if o is None or (o.mime or "") != "application/pdf":
        return None
    data = o.data
    if data is None:
        try:
            data = await storage.get_adapter().download(storage.original_key(sid))
        except Exception:  # noqa: BLE001
            return None
    res = await run_in_threadpool(render_service.render_one_page, data, page_no)
    if res is None:
        return None
    _w, _h, webp = res
    try:
        await storage.get_adapter().upload(storage.page_key(sid, page_no), webp, content_type="image/webp")
    except Exception:  # noqa: BLE001
        pass
    return webp


@router.get("/{kb_id}/sources/{source_id}/original")
async def get_source_original(kb_id: str = Path(...), source_id: str = Path(...),
                              user: CurrentUser = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db_session)) -> StreamingResponse:
    """取上传文件的原始字节(用于下载/直接渲染)。优先对象存储,降级 DB bytea。inline 展示。"""
    import io

    kb, _ = await _load(db, kb_id, user)
    try:
        sid = uuid.UUID(source_id)
    except ValueError:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "source"})
    r = await db.get(RawSource, sid)
    if r is None or r.kb_id != kb.id:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "source"})
    o = await db.get(RawSourceOriginal, sid)
    if o is None:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "original"})
    data = o.data
    if data is None:  # 字节在对象存储
        try:
            data = await storage.get_adapter().download(storage.original_key(sid))
        except Exception:  # noqa: BLE001
            raise BizError("RESOURCE_NOT_FOUND", {"resource": "original"})
    return StreamingResponse(io.BytesIO(data), media_type=o.mime or "application/octet-stream",
                             headers={"Content-Disposition": "inline"})


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
    await storage.delete_source_objects(sid)   # 清对象存储(原文 + 页面图);DB 行随级联硬删
    await db.delete(raw)   # 硬删 + 级联(chunks ON DELETE CASCADE)
    await db.commit()
    # 库内已无源 → 清空知识图谱(否则图谱残留旧实体)
    remaining = int((await db.execute(select(func.count()).select_from(RawSource)
                                      .where(RawSource.kb_id == kb.id))).scalar_one())
    if remaining == 0:
        try:
            await graph_service.drop_graph(db, kb.id)
            await db.commit()
        except Exception as e:  # noqa: BLE001
            log.warning("graph_drop_failed", kb_id=kb_id, error=str(e))
    log.info("source_deleted", kb_id=kb_id, source_id=source_id, user_id=user.user_id)
    return {"ok": True}


@router.get("/{kb_id}/search")
async def search_kb(kb_id: str = Path(...), q: str = "", limit: int = 10,
                    embed_model: str = "", rerank_model: str = "", source_id: str = "",
                    user: CurrentUser = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, _ = await _load(db, kb_id, user)
    try:
        sid = uuid.UUID(source_id) if source_id else None
    except ValueError:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "source"})
    hits = await ingest_service.search_chunks(db, kb_id=kb.id, query=q, limit=min(max(limit, 1), 50),
                                              embed_model=embed_model or None, rerank_model=rerank_model or None,
                                              raw_source_id=sid)
    return {"query": q, "hits": hits, "total": len(hits)}


async def _graph_build_bg(kb_id: uuid.UUID, job_id: uuid.UUID, sources: list[tuple[str, str]]) -> None:
    """后台构建图谱:重建前清旧 → 逐源抽取 → 实时回写进度。自带 session。"""
    from app.db.session import get_sessionmaker
    try:
        async with get_sessionmaker()() as db:
            await graph_service.drop_graph(db, kb_id)  # 重建前清旧,使图反映当前源
            await db.commit()
            n = max(1, len(sources))
            for i, (_t, txt) in enumerate(sources):
                # 处理第 i 个源前先推进度(至少 8%,单源也有可见进度);源内 LLM 抽取为原子,无法再细分
                await db.execute(text("UPDATE ingest_jobs SET progress=:p WHERE id=:id"),
                                 {"p": max(8, int(i / n * 95)), "id": str(job_id)})
                await db.commit()
                if txt and txt.strip():
                    await graph_service.build_from_text(db, kb_id, txt)
            await db.execute(text("UPDATE ingest_jobs SET status='done', progress=100 WHERE id=:id"), {"id": str(job_id)})
            await db.commit()
    except Exception as e:  # noqa: BLE001
        log.warning("graph_build_failed", kb_id=str(kb_id), error=str(e))
        try:
            async with get_sessionmaker()() as d2:
                await d2.execute(text("UPDATE ingest_jobs SET status='failed', error=:e WHERE id=:id"),
                                 {"e": str(e)[:500], "id": str(job_id)})
                await d2.commit()
        except Exception:  # noqa: BLE001
            pass


@router.post("/{kb_id}/graph/build")
async def build_graph(kb_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db_session)) -> dict:
    """启动图谱构建(后台 + 进度);需 editor/owner。返回 job 信息,前端轮询 /graph/status。"""
    kb, role = await _load(db, kb_id, user)
    if role not in ("owner", "editor"):
        raise BizError("PERM_DENIED", {"need": "editor"})
    rows = (await db.execute(select(RawSource.title, RawSource.parsed_text)
                             .where(RawSource.kb_id == kb.id, RawSource.parsed_text.is_not(None)))).all()
    sources = [(t, x) for t, x in rows]
    if not sources:
        await graph_service.drop_graph(db, kb.id)  # 没源 → 清图
        await db.commit()
        return {"job_id": None, "status": "done", "total": 0}
    job = IngestJob(kb_id=kb.id, kind="graph", status="running", progress=0)
    db.add(job)
    await db.flush()
    jid = job.id
    await db.commit()
    asyncio.create_task(_graph_build_bg(kb.id, jid, sources))
    return {"job_id": str(jid), "status": "running", "total": len(sources)}


@router.get("/{kb_id}/graph/status")
async def graph_status(kb_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db_session)) -> dict:
    """最近一次图谱构建任务的状态/进度(供前端轮询 + 刷新续接进度)。"""
    kb, _ = await _load(db, kb_id, user)
    j = (await db.execute(select(IngestJob).where(IngestJob.kb_id == kb.id, IngestJob.kind == "graph")
                          .order_by(IngestJob.created_at.desc()).limit(1))).scalar_one_or_none()
    if j is None:
        return {"status": "none", "progress": 0}
    return {"status": j.status, "progress": j.progress, "error": j.error}


@router.get("/{kb_id}/graph")
async def get_graph(kb_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db_session)) -> dict:
    kb, _ = await _load(db, kb_id, user)
    # 库内无任何源 → 图谱必为空(顺手清掉历史遗留的孤儿图,保证「删完源图就空」)
    n_src = int((await db.execute(select(func.count()).select_from(RawSource)
                                  .where(RawSource.kb_id == kb.id))).scalar_one())
    if n_src == 0:
        try:
            await graph_service.drop_graph(db, kb.id)
            await db.commit()
        except Exception as e:  # noqa: BLE001
            log.warning("graph_drop_failed", kb_id=kb_id, error=str(e))
        return {"nodes": [], "edges": []}
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


async def _wiki_compile_bg(kb_id: uuid.UUID, ws_id: uuid.UUID, kb_name: str,
                           job_id: uuid.UUID, sources: list[tuple[str, str]]) -> None:
    """后台编译 Wiki + 回写 job 进度(状态持久化,前端刷新可续看)。自带 session。"""
    from app.db.session import get_sessionmaker
    try:
        async with get_sessionmaker()() as db:
            await db.execute(text("UPDATE ingest_jobs SET progress=25 WHERE id=:id"), {"id": str(job_id)})
            await db.commit()
            page = await wiki_service.compile_overview(db, kb_id, ws_id, kb_name, sources)
            ok = page is not None
            await db.execute(text("UPDATE ingest_jobs SET status=:s, progress=100, error=:e WHERE id=:id"),
                             {"s": "done" if ok else "failed", "e": None if ok else "no_sources", "id": str(job_id)})
            await db.commit()
    except Exception as e:  # noqa: BLE001
        log.warning("wiki_compile_failed", kb_id=str(kb_id), error=str(e))
        try:
            async with get_sessionmaker()() as d2:
                await d2.execute(text("UPDATE ingest_jobs SET status='failed', error=:e WHERE id=:id"),
                                 {"e": str(e)[:500], "id": str(job_id)})
                await d2.commit()
        except Exception:  # noqa: BLE001
            pass


@router.post("/{kb_id}/wiki/compile")
async def compile_wiki(kb_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db_session)) -> dict:
    """知识复利:把库内各源 LLM 编译成结构化 Wiki 概览页(后台 + 进度)。需 editor/owner。"""
    kb, role = await _load(db, kb_id, user)
    if role not in ("owner", "editor"):
        raise BizError("PERM_DENIED", {"need": "editor"})
    rows = (await db.execute(select(RawSource.title, RawSource.parsed_text)
                             .where(RawSource.kb_id == kb.id, RawSource.parsed_text.is_not(None)))).all()
    if not rows:
        return {"job_id": None, "status": "failed", "reason": "no_sources"}
    job = IngestJob(kb_id=kb.id, kind="wiki", status="running", progress=0)
    db.add(job)
    await db.flush()
    jid = job.id
    await db.commit()
    asyncio.create_task(_wiki_compile_bg(kb.id, kb.workspace_id, kb.name, jid, [(t, x) for t, x in rows]))
    return {"job_id": str(jid), "status": "running"}


@router.get("/{kb_id}/wiki/status")
async def wiki_status(kb_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db_session)) -> dict:
    """最近一次 Wiki 编译任务的状态/进度(供前端轮询 + 刷新续接进度)。"""
    kb, _ = await _load(db, kb_id, user)
    j = (await db.execute(select(IngestJob).where(IngestJob.kb_id == kb.id, IngestJob.kind == "wiki")
                          .order_by(IngestJob.created_at.desc()).limit(1))).scalar_one_or_none()
    if j is None:
        return {"status": "none", "progress": 0}
    return {"status": j.status, "progress": j.progress, "error": j.error}


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
    source_id: str | None = Field(default=None)  # 指定 → 仅基于该文档问答(文档级问答)


@router.post("/{kb_id}/chat")
async def chat_kb(body: ChatIn, kb_id: str = Path(...),
                  user: CurrentUser = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db_session)) -> StreamingResponse:
    """RAG 引用问答(SSE)。先发 sources(检索到的带编号切片),再流式发答案 delta,最后 done。
    注:检索 + 取渠道在返回前完成(DB 会话此时存活);生成器内只用已取好的渠道字段调模型,不碰 DB。"""
    kb, _ = await _load(db, kb_id, user)
    try:
        ssid = uuid.UUID(body.source_id) if body.source_id else None
    except ValueError:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "source"})
    hits = await ingest_service.search_chunks(db, kb_id=kb.id, query=body.query, limit=body.top_k,
                                              raw_source_id=ssid)
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

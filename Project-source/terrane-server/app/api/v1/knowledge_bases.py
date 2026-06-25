"""Knowledge base API (frontend /api/v1/knowledge-bases, platform database terrane_main).

A KB = a container for compounding knowledge (raw sources -> compile -> Wiki + graph). These
endpoints first cover the KB entity itself: CRUD + visibility/KB-role ACL; ingestion/retrieval/graph
come in later endpoints. Visibility: private (owner + explicit members) / shared (explicit members) /
workspace (visible to this workspace). ACL: owner has full control; KB editor can edit; only the owner
can delete; any access grants read. The License-locked state is intercepted by middleware.
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
    graph_service, ingest_service, memory_service, render_service, retrieval_service, storage,
    studio_service, wiki_service,
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
    """Return the user's effective role on the KB: owner / editor / viewer / None (no access)."""
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
    """KBs visible to the current user: owned + workspace-visible in this workspace + explicitly shared (kb_member)."""
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
        await graph_service.drop_graph(db, kb.id)   # The AGE graph is independent of relational tables; drop it together with the KB
        await db.commit()
    except Exception as e:  # noqa: BLE001
        log.warning("graph_drop_failed", kb_id=kb_id, error=str(e))
    # Clear object storage: originals + page images of every source in the KB (DB rows are hard-deleted by cascade, but object storage must be cleared explicitly)
    sids = (await db.execute(select(RawSource.id).where(RawSource.kb_id == kb.id))).scalars().all()
    for s in sids:
        await storage.delete_source_objects(s)
    await db.delete(kb)   # Hard delete + cascade (kb_members/raw_sources/chunks/wiki/jobs)
    await db.commit()
    log.info("kb_deleted", kb_id=kb_id, user_id=user.user_id)
    return {"ok": True}


# ---- KB sharing (kb_members: owner invites users from the same workspace as viewer/editor) ----

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


# ---- Source ingestion + retrieval (first stage of compounding knowledge: text in -> chunk -> lexical search) ----

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
    """Upload a file -> parse with Terrane Parse -> ingest as chunks/embeddings.
    tier parse level: fast = lexical only; standard = lexical + VL (images/scans); high = full-page VL layout parsing (high-fidelity tables/formulas/layout)."""
    if tier not in ("fast", "standard", "high"):
        tier = "standard"
    kb, role = await _load(db, kb_id, user)
    if role not in ("owner", "editor"):
        raise BizError("PERM_DENIED", {"need": "editor"})
    data = await file.read()
    fname = file.filename or "upload"
    ext = os.path.splitext(fname)[1].lower()
    mime = _EXT_MIME.get(ext, file.content_type or "")
    cap = 300_000_000 if mime in video_parser.VIDEO_MIMES else 30_000_000  # Higher cap for video
    if len(data) > cap:
        raise BizError("VALIDATION_FAILED", {"reason": "file_too_large"})

    is_text = mime not in video_parser.VIDEO_MIMES and mime not in parse_engine.SUPPORTED
    if is_text:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise BizError("VALIDATION_FAILED", {"reason": "unsupported_file_type"})

    # First create a "parsing" source, persist the original/render, and return immediately; parsing + ingestion run asynchronously (high-fidelity VL is slow, so the upload should not block).
    raw = await ingest_service.create_pending_source(
        db, kb_id=kb.id, workspace_id=kb.workspace_id, title=fname, mime=mime, size=len(data))
    if mime not in video_parser.VIDEO_MIMES:
        in_obj = False
        try:
            await storage.ensure_bucket()
            await storage.get_adapter().upload(storage.original_key(raw.id), data,
                                               content_type=mime or "application/octet-stream")
            in_obj = True
        except Exception as e:  # noqa: BLE001 -- object storage unavailable -> fall back to DB
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
    """Parse a file by tier -> Markdown text. None/empty string = failure."""
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
        if mime == "application/pdf" and tier == "high":  # High fidelity: full-page VL layout parsing
            try:
                text = await parse_vl.parse_pdf_fullvl(db, data)
            except Exception as e:  # noqa: BLE001
                log.warning("vl_fullparse_failed", error=str(e))
        if not text:  # fast/standard, or high-fidelity fallback -> lexical
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
            if text and mime == "application/pdf" and tier != "fast":  # Standard: + VL image/scan enhancement
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
    """Background: parse by tier -> write source + chunks/embeddings; on failure set status=failed. Manages its own session."""
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
    """Re-parse (change tier / retry after failure): fetch the original -> re-parse + re-ingest by tier in the background. Requires editor/owner."""
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
        raise BizError("VALIDATION_FAILED", {"reason": "no_original"})  # No original (e.g. pasted text) cannot be re-parsed
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
    """Get a single source's parsed content (preview). Returns the Terrane Parse output text + metadata + chunk count."""
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
    # The original file's true mime (RawSource.mime is uniformly set to text/plain at ingestion; the left-pane render needs the original file's real mime)
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
    """Get metadata for the per-page WebP layout images of the original (page count + per-page size). The frontend uses this to lay out placeholders and lazy-load individual pages by viewport."""
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
    """Get a single-page WebP layout image (from object storage). Strong caching: page image content is immutable."""
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
    except Exception:  # noqa: BLE001 -- page not rendered yet -> on-demand instant render for large documents (PDF only)
        data = await _ondemand_page(db, sid, page_no)
        if data is None:
            raise BizError("RESOURCE_NOT_FOUND", {"resource": "page"})
    return StreamingResponse(io.BytesIO(data), media_type="image/webp",
                             headers={"Content-Disposition": "inline", "Cache-Control": "public, max-age=31536000, immutable"})


async def _ondemand_page(db: AsyncSession, sid: uuid.UUID, page_no: int) -> bytes | None:
    """On-demand single-page render (when scrolling to a page not yet progressively rendered): fetch the original PDF -> render that page -> store it back -> return the bytes.
    PDF only (Office files rely on background progressive rendering; converting a single page again is too costly)."""
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
    """Get the raw bytes of the uploaded file (for download/direct rendering). Prefer object storage, fall back to DB bytea. Displayed inline."""
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
    if data is None:  # Bytes live in object storage
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
    await storage.delete_source_objects(sid)   # Clear object storage (original + page images); DB rows are hard-deleted by cascade
    await db.delete(raw)   # Hard delete + cascade (chunks ON DELETE CASCADE)
    await db.commit()
    # No sources left in the KB -> clear the knowledge graph (otherwise stale entities linger)
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
async def search_kb(kb_id: str = Path(...), q: str = "", limit: int = 10, mode: str = "auto",
                    embed_model: str = "", rerank_model: str = "", source_id: str = "",
                    user: CurrentUser = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db_session)) -> dict:
    """Retrieval 2.0 unified search. mode: fast | deep | auto. Deep results carry a section/page citation path."""
    kb, _ = await _load(db, kb_id, user)
    try:
        sid = uuid.UUID(source_id) if source_id else None
    except ValueError:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "source"})
    mode = mode if mode in ("fast", "deep", "auto") else "auto"
    hits = await retrieval_service.retrieve(db, kb_id=kb.id, query=q, mode=mode,
                                            limit=min(max(limit, 1), 50), source_id=sid,
                                            embed_model=embed_model or None, rerank_model=rerank_model or None)
    eff = hits[0]["mode"] if hits else (retrieval_service.classify(q) if mode == "auto" else mode)
    return {"query": q, "hits": hits, "total": len(hits), "mode": eff}


async def _graph_build_bg(kb_id: uuid.UUID, job_id: uuid.UUID, sources: list[tuple[str, str]]) -> None:
    """Build the graph in the background: drop the old graph before rebuild -> extract source by source -> write progress back in real time. Manages its own session."""
    from app.db.session import get_sessionmaker
    try:
        async with get_sessionmaker()() as db:
            await graph_service.drop_graph(db, kb_id)  # Drop the old graph before rebuild so it reflects the current sources
            await db.commit()
            n = max(1, len(sources))
            for i, (_t, txt) in enumerate(sources):
                # Advance progress before processing source i (at least 8%, so even a single source shows visible progress); LLM extraction within a source is atomic and cannot be subdivided further
                await db.execute(text("UPDATE ingest_jobs SET progress=:p WHERE id=:id"),
                                 {"p": max(8, int(i / n * 95)), "id": str(job_id)})
                await db.commit()
                if txt and txt.strip():
                    await graph_service.build_from_text(db, kb_id, txt)
            # Retrieval 2.0: (re)build the RAPTOR semantic summary tree alongside the graph (KB-wide, bounded).
            try:
                await retrieval_service.build_semantic_tree(db, kb_id)
            except Exception as se:  # noqa: BLE001
                log.warning("semantic_tree_skipped", kb_id=str(kb_id), error=str(se))
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
    """Start graph construction (background + progress); requires editor/owner. Returns job info; the frontend polls /graph/status."""
    kb, role = await _load(db, kb_id, user)
    if role not in ("owner", "editor"):
        raise BizError("PERM_DENIED", {"need": "editor"})
    rows = (await db.execute(select(RawSource.title, RawSource.parsed_text)
                             .where(RawSource.kb_id == kb.id, RawSource.parsed_text.is_not(None)))).all()
    sources = [(t, x) for t, x in rows]
    if not sources:
        await graph_service.drop_graph(db, kb.id)  # No sources -> clear the graph
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
    """Status/progress of the most recent graph build job (for frontend polling + resuming progress after refresh)."""
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
    # No sources in the KB -> the graph must be empty (also clear any leftover orphan graph, so "deleting all sources empties the graph")
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
    """Studio generation (NotebookLM-style): study_guide/faq/briefing/timeline/mind_map/flashcards/quiz/data_table."""
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
    """Studio media: two-host podcast audio (TTS), returns {script, audio(data url)}."""
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
    """Studio media: export the slide deck as a .pptx download."""
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
    """Agent Lint health check: scan KB health (sources/chunks/embeddings/graph/Wiki) and produce an issue list + score."""
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
        issues.append({"level": "info", "code": "no_sources", "msg": "This knowledge base has no materials yet."})
    if n_failed:
        issues.append({"level": "warn", "code": "failed_sources", "msg": f"{n_failed} source(s) failed to parse."})
    if n_chunk and n_embed < n_chunk:
        issues.append({"level": "warn", "code": "unembedded", "msg": f"{n_chunk - n_embed}/{n_chunk} chunks have no vector (embedding channel not configured or failed); vector search is incomplete."})
    if n_src and not has_graph:
        issues.append({"level": "info", "code": "no_graph", "msg": "The knowledge graph has not been built yet; click \"Build graph\" to generate it."})
    if n_src and wiki is None:
        issues.append({"level": "info", "code": "no_wiki", "msg": "The Wiki has not been compiled yet; click \"Compile Wiki\" to generate it."})

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
    """Compile the Wiki in the background + write job progress back (state is persisted, so a frontend refresh can resume viewing). Manages its own session."""
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
    """Compounding knowledge: have the LLM compile the KB's sources into a structured Wiki overview page (background + progress). Requires editor/owner."""
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
    """Status/progress of the most recent Wiki compile job (for frontend polling + resuming progress after refresh)."""
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


# ---- MCP keys (Bearer tokens for mounting the KB into Claude/Cursor, scoped to this KB) ----

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
    # The token is returned only this once
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
    model: str | None = Field(default=None, max_length=128)  # Model selected in the frontend "Model settings" (optional)
    source_id: str | None = Field(default=None)  # If set -> answer based only on this document (document-level Q&A)
    mode: str = Field(default="auto")  # Retrieval 2.0: fast | deep | auto


@router.post("/{kb_id}/chat")
async def chat_kb(body: ChatIn, kb_id: str = Path(...),
                  user: CurrentUser = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db_session)) -> StreamingResponse:
    """RAG citation Q&A (SSE). First emit sources (the retrieved, numbered chunks), then stream answer deltas, then done.
    Note: retrieval + channel lookup complete before returning (while the DB session is alive); inside the generator we only use the already-fetched channel fields to call the model and never touch the DB."""
    kb, _ = await _load(db, kb_id, user)
    try:
        ssid = uuid.UUID(body.source_id) if body.source_id else None
    except ValueError:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "source"})
    mode = body.mode if body.mode in ("fast", "deep", "auto") else "auto"
    hits = await retrieval_service.retrieve(db, kb_id=kb.id, query=body.query, mode=mode,
                                            limit=body.top_k, source_id=ssid)
    ch = (await get_channel_by_model(db, "chat", body.model)) if body.model else None
    if ch is None:
        ch = await get_channel(db, "chat")
    src = [{"n": i + 1, "source_title": h["source_title"], "source_id": h["source_id"],
            "content": h["content"], "score": h["score"],
            "citation_path": h.get("citation_path"), "page_start": h.get("page_start"),
            "page_end": h.get("page_end")} for i, h in enumerate(hits)]

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

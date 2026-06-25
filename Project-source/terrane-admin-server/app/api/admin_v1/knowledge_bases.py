"""Admin "Knowledge Base Overview" — a platform-wide view of the knowledge bases across all workspaces (read-only metadata, no content access). Mounted at /admin-api/v1/knowledge-bases."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.platform import get_platform_db
from app.models.platform.knowledge_base import KnowledgeBase
from app.models.platform.workspace import Workspace
from app.permissions.deps import require_perm
from app.permissions.registry import P

log = structlog.get_logger("terrane.admin.kb")

router = APIRouter(prefix="/admin-api/v1", tags=["kb-overview"])


@router.get("/knowledge-bases")
async def list_knowledge_bases(
    _=Depends(require_perm(P.WORKSPACE_READ)),
    pdb: AsyncSession = Depends(get_platform_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str = Query(""),
    visibility: str = Query(""),
) -> dict:
    stmt = select(KnowledgeBase, Workspace.name).join(
        Workspace, Workspace.id == KnowledgeBase.workspace_id, isouter=True)
    if q:
        stmt = stmt.where(or_(KnowledgeBase.name.ilike(f"%{q}%"), KnowledgeBase.slug.ilike(f"%{q}%")))
    if visibility in ("private", "shared", "workspace"):
        stmt = stmt.where(KnowledgeBase.visibility == visibility)

    total = int((await pdb.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one())
    rows = (await pdb.execute(stmt.order_by(KnowledgeBase.created_at.desc())
                             .offset((page - 1) * page_size).limit(page_size))).all()

    # Source counts (aggregated in one query to avoid N+1)
    src_counts = dict((await pdb.execute(text(
        "SELECT kb_id, count(*) FROM raw_sources GROUP BY kb_id"))).all())

    items = [{
        "id": str(kb.id), "name": kb.name, "slug": kb.slug, "visibility": kb.visibility,
        "status": kb.status, "workspace_name": ws_name or "—",
        "source_count": int(src_counts.get(kb.id, 0)),
        "created_at": kb.created_at.isoformat() if kb.created_at else None,
    } for kb, ws_name in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}

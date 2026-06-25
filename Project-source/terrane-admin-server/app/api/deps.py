"""FastAPI dependencies — DB session, current user (resolved from the server-side session cookie). Ported from Forge."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import BizError
from app.db.session import get_db_session
from app.services.session_service import SessionService


@dataclass
class CurrentUser:
    user_id: str
    role: str
    permissions: list[str]
    twofa_verified: bool
    name: str | None = None


async def get_current_user(request: Request) -> CurrentUser:
    """Resolve the authenticated operator from the server-side session (HttpOnly cookie)."""
    sid = request.cookies.get(get_settings().session_cookie_name)
    if not sid:
        raise BizError("AUTH_REQUIRED")
    data = await SessionService().get(sid)
    if not data:
        raise BizError("AUTH_REQUIRED")
    return CurrentUser(
        user_id=data["user_id"],
        role=data["role"],
        permissions=data.get("permissions", []),
        twofa_verified=data.get("twofa_verified", False),
        name=data.get("name"),
    )


def audit_ctx(request: Request) -> dict:
    """Common audit fields (ip / user-agent / request_id)."""
    return {
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:512],
        "request_id": getattr(request.state, "request_id", None),
    }


DbSession = Depends(get_db_session)
__all__ = ["CurrentUser", "get_current_user", "get_db_session", "AsyncSession", "audit_ctx"]

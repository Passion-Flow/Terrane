"""FastAPI 依赖 — DB session（平台库）+ 当前用户（前台 session cookie）。"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import BizError
from app.db.session import get_db_session
from app.services.session_service import SessionService

__all__ = ["CurrentUser", "get_current_user", "get_db_session"]


@dataclass
class CurrentUser:
    user_id: str
    workspace_id: str
    role: str
    twofa_verified: bool


async def get_current_user(request: Request) -> CurrentUser:
    """从服务端 session（HttpOnly cookie）解析已认证前台用户。"""
    sid = request.cookies.get(get_settings().session_cookie_name)
    if not sid:
        raise BizError("AUTH_REQUIRED")
    data = await SessionService().get(sid)
    if not data:
        raise BizError("AUTH_REQUIRED")
    return CurrentUser(
        user_id=data["user_id"],
        workspace_id=data.get("workspace_id", ""),
        role=data.get("role", "Member"),
        twofa_verified=data.get("twofa_verified", False),
    )

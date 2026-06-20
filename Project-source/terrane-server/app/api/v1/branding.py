"""公开品牌（白标）端点（/api/v1/branding）— 免登录、锁定态可取。

前台 Logo / 标签页标题 / 登录页副标题在认证前即需展示部署方品牌，故本端点不挂认证、
且在 license_gate 白名单内（锁定态仍返回）。只读，缺失返回出厂默认（页面化零配置铁律）。
品牌写入在后台管理端（terrane-admin-api 的 settings/wizard）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.models.branding import SINGLETON_ID, Branding

router = APIRouter(prefix="/api/v1/branding", tags=["branding"])


@router.get("")
async def public_branding(db: AsyncSession = Depends(get_db_session)) -> dict:
    b = await db.get(Branding, SINGLETON_ID)
    return {
        "product_name": b.product_name if b else "Terrane",
        "logo_data": b.logo_data if b else None,
        "login_logo": b.login_logo if b else None,
        "favicon": b.favicon if b else None,
        "accent_color": b.accent_color if b else "#0f9b8e",
        "login_subtitle": b.login_subtitle if b else None,
        "support_url": b.support_url if b else None,
        "enabled": b.enabled if b else True,
    }

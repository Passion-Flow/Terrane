"""公开品牌（白标）端点（/admin-api/v1/branding）— 免登录、锁定态可取。

登录页 / 激活页 / 侧边栏在认证前就要显示部署方品牌（产品名 / 主题色 / 登录副标题），
故本端点不挂认证、且在 license_gate 白名单内（锁定态仍返回）。只读，缺失返回出厂默认
（页面化零配置铁律）。写入走 settings/wizard 的 PATCH/POST（鉴权）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.platform import get_platform_db
from app.services.platform_settings import get_branding

router = APIRouter(prefix="/admin-api/v1/branding", tags=["branding"])


@router.get("")
async def public_branding(pdb: AsyncSession = Depends(get_platform_db)) -> dict:
    b = await get_branding(pdb)
    return {
        "product_name": b.product_name,
        "logo_data": b.logo_data,
        "login_logo": b.login_logo,
        "favicon": b.favicon,
        "accent_color": b.accent_color,
        "login_subtitle": b.login_subtitle,
        "support_url": b.support_url,
        "enabled": b.enabled,
    }

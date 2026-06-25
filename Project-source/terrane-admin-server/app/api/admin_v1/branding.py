"""Public branding (white-label) endpoint (/admin-api/v1/branding) — no login required, available even in the locked state.

The login page / activation page / sidebar must show the deployer's branding (product name / accent color / login subtitle) before authentication,
so this endpoint has no auth and is on the license_gate allowlist (still returns in the locked state). Read-only; falls back to factory defaults when missing
(page-based zero-config rule). Writes go through the PATCH/POST endpoints of settings/wizard (authenticated).
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

"""Public branding (white-label) endpoint (/api/v1/branding) — no login required, available even when locked.

The frontend logo / tab title / login-page subtitle must show the deployer's branding before authentication,
so this endpoint requires no auth and is on the license_gate allowlist (still returns when locked). Read-only;
when absent it returns the factory defaults (page-based zero-config rule).
Branding is written from the admin console (settings/wizard in terrane-admin-api).
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

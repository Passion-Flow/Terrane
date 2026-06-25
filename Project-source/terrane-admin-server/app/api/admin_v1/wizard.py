"""Setup wizard API (/admin-api/v1/wizard) — License -> super admin -> email -> branding -> complete.

Super admin only (PRD: wizard is mandatory on first launch). Config is written to the platform DB terrane_main (settings/branding),
and changes are recorded in audit_logs (append-only). Encryption of the email password field is pending the KEK infrastructure (currently stored in plaintext + __enc flag,
consistent with the 2FA placeholder; never returned to the frontend -> redacted on GET).
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, audit_ctx, get_current_user, get_db_session
from app.core.errors import BizError
from app.db.platform import get_platform_db
from app.repositories.user import UserRepository
from app.schemas.wizard import BrandingIn, EmailConfigIn, EmailTestIn, WizardStateOut
from app.services import audit_service, email_service, wizard_service
from app.services.platform_settings import (
    EMAIL_KEY,
    WIZARD_KEY,
    get_branding,
    get_setting,
    set_setting,
)

log = structlog.get_logger("terrane.admin.wizard")

router = APIRouter(prefix="/admin-api/v1/wizard", tags=["wizard"])


def _require_super_admin(user: CurrentUser) -> None:
    if user.role != "super_admin" and "*" not in user.permissions:
        raise BizError("PERM_DENIED", {"need": "super_admin"})


async def _super_admin_done(admin_db: AsyncSession, user: CurrentUser) -> bool:
    db_user = await UserRepository(admin_db).get(uuid.UUID(user.user_id))
    return bool(db_user and not db_user.must_change_password)


@router.get("")
async def get_wizard(user: CurrentUser = Depends(get_current_user),
                     admin_db: AsyncSession = Depends(get_db_session),
                     pdb: AsyncSession = Depends(get_platform_db)) -> WizardStateOut:
    _require_super_admin(user)
    sa_done = await _super_admin_done(admin_db, user)
    state = await wizard_service.get_state(pdb, super_admin_done=sa_done)
    return WizardStateOut(**state)


@router.post("/email")
async def save_email(body: EmailConfigIn, request: Request,
                     user: CurrentUser = Depends(get_current_user),
                     pdb: AsyncSession = Depends(get_platform_db)) -> dict:
    _require_super_admin(user)
    existing = await get_setting(pdb, EMAIL_KEY) or {}
    # Empty password = keep the existing one (avoids the masked-asterisk echo overwriting it with blank).
    password = body.password or existing.get("password", "")
    cfg = {
        "provider": "smtp", "host": body.host, "port": body.port,
        "encryption": body.encryption, "username": body.username, "password": password,
        "from_address": str(body.from_address), "from_name": body.from_name,
        "allow_insecure": body.allow_insecure,
        "configured": True, "__enc": False,  # TODO: route password through [L5-ENC] once KEK lands
    }
    await set_setting(pdb, EMAIL_KEY, cfg)
    await audit_service.record(
        pdb, action="wizard.email.configure", actor_id=user.user_id, actor_name=user.name,
        target_type="setting", target_id=EMAIL_KEY,
        after={"host": body.host, "port": body.port, "encryption": body.encryption,
               "from_address": str(body.from_address), "has_password": bool(password)},  # redacted
        **audit_ctx(request))
    await pdb.commit()
    return {"data": {"ok": True}}


@router.post("/email/test")
async def test_email(body: EmailTestIn, user: CurrentUser = Depends(get_current_user),
                     pdb: AsyncSession = Depends(get_platform_db)) -> dict:
    """Send a test email using the currently saved email config (save first, then test)."""
    _require_super_admin(user)
    cfg = await get_setting(pdb, EMAIL_KEY)
    if not cfg or not cfg.get("configured"):
        raise BizError("VALIDATION_FAILED", {"reason": "email_not_configured"})
    await email_service.test_smtp(cfg, to=str(body.to))
    return {"data": {"ok": True}}


@router.post("/branding")
async def save_branding(body: BrandingIn, request: Request,
                        user: CurrentUser = Depends(get_current_user),
                        pdb: AsyncSession = Depends(get_platform_db)) -> dict:
    _require_super_admin(user)
    branding = await get_branding(pdb)
    before = {"product_name": branding.product_name, "accent_color": branding.accent_color}
    branding.product_name = body.product_name
    branding.logo_data = body.logo_data
    branding.accent_color = body.accent_color
    branding.login_subtitle = body.login_subtitle
    branding.support_url = body.support_url
    wiz = await get_setting(pdb, WIZARD_KEY) or {}
    wiz["branding_done"] = True
    await set_setting(pdb, WIZARD_KEY, wiz)
    await audit_service.record(
        pdb, action="wizard.branding.update", actor_id=user.user_id, actor_name=user.name,
        target_type="branding", target_id="singleton",
        before=before, after={"product_name": body.product_name, "accent_color": body.accent_color},
        **audit_ctx(request))
    await pdb.commit()
    return {"data": {"ok": True}}


@router.post("/complete")
async def complete_wizard(request: Request, user: CurrentUser = Depends(get_current_user),
                          admin_db: AsyncSession = Depends(get_db_session),
                          pdb: AsyncSession = Depends(get_platform_db)) -> dict:
    _require_super_admin(user)
    if not await _super_admin_done(admin_db, user):
        raise BizError("VALIDATION_FAILED", {"reason": "super_admin_password_unchanged"})
    wiz = await get_setting(pdb, WIZARD_KEY) or {}
    if wiz.get("completed"):
        raise BizError("WIZARD_ALREADY_DONE")
    wiz["completed"] = True
    await set_setting(pdb, WIZARD_KEY, wiz)
    await audit_service.record(
        pdb, action="wizard.complete", actor_id=user.user_id, actor_name=user.name,
        **audit_ctx(request))
    await pdb.commit()
    log.info("wizard_completed", actor_id=user.user_id)
    return {"data": {"ok": True}}

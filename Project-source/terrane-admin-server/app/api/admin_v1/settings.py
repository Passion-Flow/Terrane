"""后台设置 API（/admin-api/v1/settings）— 向导完成后随时编辑邮件 / 品牌。

写平台库 terrane_main（system_settings + branding），变更落 audit_logs（append-only）。
复用向导同款服务（platform_settings / email_service / email_presets / 脱敏器），
与 wizard.py 区别：不触碰向导步骤标记（email_done/branding_done/completed），纯设置面。
权限：SETTINGS_READ / SETTINGS_WRITE（平台角色映射，super_admin=*）。
邮件密码仍明文存储 + __enc 标记（KEK 基建落地前），GET 一律脱敏不回传。
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, audit_ctx
from app.core.errors import BizError
from app.db.platform import get_platform_db
from app.permissions.deps import require_perm
from app.permissions.registry import P
from app.schemas.wizard import BrandingIn, EmailConfigIn, EmailTestIn
from app.services import audit_service, email_service
from app.services.email_presets import all_presets
from app.services import crypto
from app.services.platform_settings import (
    EMAIL_KEY,
    SECURITY_KEY,
    get_branding,
    get_security_policy,
    get_setting,
    set_setting,
)
from app.services.wizard_service import _mask_email

log = structlog.get_logger("terrane.admin.settings")

router = APIRouter(prefix="/admin-api/v1/settings", tags=["settings"])


@router.get("")
async def get_settings(
    _=Depends(require_perm(P.SETTINGS_READ)),
    pdb: AsyncSession = Depends(get_platform_db),
) -> dict:
    """设置面快照：邮件（脱敏）+ 品牌 + 邮箱服务商预设（一键填充）。"""
    email_cfg = await get_setting(pdb, EMAIL_KEY) or {}
    branding = await get_branding(pdb)
    return {
        "email": {"configured": bool(email_cfg.get("configured")), **_mask_email(email_cfg)},
        "branding": {
            "product_name": branding.product_name,
            "logo_data": branding.logo_data,
            "login_logo": branding.login_logo,
            "favicon": branding.favicon,
            "accent_color": branding.accent_color,
            "login_subtitle": branding.login_subtitle,
            "support_url": branding.support_url,
            "enabled": branding.enabled,
        },
        "email_presets": all_presets(),
    }


@router.patch("/email")
async def update_email(
    body: EmailConfigIn, request: Request,
    user: CurrentUser = Depends(require_perm(P.SETTINGS_WRITE)),
    pdb: AsyncSession = Depends(get_platform_db),
) -> dict:
    """保存邮件（SMTP）配置。密码留空 = 沿用既有（避免脱敏回填覆盖为空）。"""
    existing = await get_setting(pdb, EMAIL_KEY) or {}
    # 新密码 → KEK 加密;留空 → 沿用既有(已是密文)
    if body.password:
        password = crypto.encrypt(body.password)
    else:
        password = existing.get("password", "")
    cfg = {
        "provider": "smtp", "host": body.host, "port": body.port,
        "encryption": body.encryption, "username": body.username, "password": password,
        "from_address": str(body.from_address), "from_name": body.from_name,
        "allow_insecure": body.allow_insecure,
        "configured": True, "__enc": crypto.is_encrypted(password),  # L5-ENC
    }
    await set_setting(pdb, EMAIL_KEY, cfg)
    await audit_service.record(
        pdb, action="settings.email.update", actor_id=user.user_id, actor_name=user.name,
        target_type="setting", target_id=EMAIL_KEY,
        after={"host": body.host, "port": body.port, "encryption": body.encryption,
               "from_address": str(body.from_address), "has_password": bool(password)},  # 脱敏
        **audit_ctx(request))
    await pdb.commit()
    return {"data": {"ok": True}}


@router.post("/email/test")
async def test_email(
    body: EmailTestIn,
    _: CurrentUser = Depends(require_perm(P.SETTINGS_WRITE)),
    pdb: AsyncSession = Depends(get_platform_db),
) -> dict:
    """用当前已保存的邮件配置发一封测试邮件（须先保存）。"""
    cfg = await get_setting(pdb, EMAIL_KEY)
    if not cfg or not cfg.get("configured"):
        raise BizError("VALIDATION_FAILED", {"reason": "email_not_configured"})
    await email_service.test_smtp(cfg, to=str(body.to))
    return {"data": {"ok": True}}


class SecurityPolicyIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    password_min_length: int = Field(ge=8, le=128)
    password_require_char_classes: int = Field(ge=1, le=4)
    login_lock_threshold: int = Field(ge=3, le=50)
    login_lock_seconds: int = Field(ge=60, le=86_400)            # 1 分钟 – 24 小时
    session_absolute_ttl_seconds: int = Field(ge=3_600, le=31_536_000)  # 1 小时 – 365 天


@router.get("/security")
async def get_security(
    _=Depends(require_perm(P.SETTINGS_READ)),
    pdb: AsyncSession = Depends(get_platform_db),
) -> dict:
    """安全策略快照（密码规则，覆盖于出厂默认之上）。"""
    return await get_security_policy(pdb)


@router.patch("/security")
async def update_security(
    body: SecurityPolicyIn, request: Request,
    user: CurrentUser = Depends(require_perm(P.SETTINGS_WRITE)),
    pdb: AsyncSession = Depends(get_platform_db),
) -> dict:
    """保存安全策略（密码最小长度 / 字符类别数）。前后台所有口令校验点立即生效。"""
    cfg = {
        "password_min_length": body.password_min_length,
        "password_require_char_classes": body.password_require_char_classes,
        "login_lock_threshold": body.login_lock_threshold,
        "login_lock_seconds": body.login_lock_seconds,
        "session_absolute_ttl_seconds": body.session_absolute_ttl_seconds,
    }
    await set_setting(pdb, SECURITY_KEY, cfg)
    await audit_service.record(
        pdb, action="settings.security.update", actor_id=user.user_id, actor_name=user.name,
        target_type="setting", target_id=SECURITY_KEY, after=cfg, **audit_ctx(request))
    await pdb.commit()
    return {"data": {"ok": True}}


@router.patch("/branding")
async def update_branding(
    body: BrandingIn, request: Request,
    user: CurrentUser = Depends(require_perm(P.SETTINGS_WRITE)),
    pdb: AsyncSession = Depends(get_platform_db),
) -> dict:
    """保存白标（产品名 / 主题色 / 登录副标题 / Logo / 支持链接）。"""
    branding = await get_branding(pdb)
    before = {"product_name": branding.product_name, "accent_color": branding.accent_color}
    branding.product_name = body.product_name
    branding.logo_data = body.logo_data
    branding.login_logo = body.login_logo
    branding.favicon = body.favicon
    branding.accent_color = body.accent_color
    branding.login_subtitle = body.login_subtitle
    branding.support_url = body.support_url
    await audit_service.record(
        pdb, action="settings.branding.update", actor_id=user.user_id, actor_name=user.name,
        target_type="branding", target_id="singleton",
        before=before, after={"product_name": body.product_name, "accent_color": body.accent_color},
        **audit_ctx(request))
    await pdb.commit()
    return {"data": {"ok": True}}


# ── SSO（OIDC 企业登录）配置 ──
SSO_KEY = "sso"


class SsoConfigIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    enabled: bool = False
    issuer: str = Field(default="", max_length=512)
    client_id: str = Field(default="", max_length=255)
    client_secret: str = Field(default="", max_length=512)   # 留空 = 沿用既有
    scopes: str = Field(default="openid email profile", max_length=255)
    label: str = Field(default="企业 SSO", max_length=64)


@router.get("/sso")
async def get_sso(_=Depends(require_perm(P.SETTINGS_READ)),
                  pdb: AsyncSession = Depends(get_platform_db)) -> dict:
    cfg = await get_setting(pdb, SSO_KEY) or {}
    return {"data": {"enabled": bool(cfg.get("enabled")), "issuer": cfg.get("issuer", ""),
                     "client_id": cfg.get("client_id", ""), "scopes": cfg.get("scopes", "openid email profile"),
                     "label": cfg.get("label", "企业 SSO"), "has_secret": bool(cfg.get("client_secret"))}}


@router.patch("/sso")
async def update_sso(body: SsoConfigIn, request: Request,
                     user: CurrentUser = Depends(require_perm(P.SETTINGS_WRITE)),
                     pdb: AsyncSession = Depends(get_platform_db)) -> dict:
    existing = await get_setting(pdb, SSO_KEY) or {}
    secret = crypto.encrypt(body.client_secret) if body.client_secret else existing.get("client_secret", "")
    cfg = {"enabled": body.enabled, "issuer": body.issuer.rstrip("/"), "client_id": body.client_id,
           "client_secret": secret, "scopes": body.scopes, "label": body.label, "__enc": crypto.is_encrypted(secret)}
    await set_setting(pdb, SSO_KEY, cfg)
    await audit_service.record(
        pdb, action="settings.sso.update", actor_id=user.user_id, actor_name=user.name,
        target_type="setting", target_id=SSO_KEY,
        after={"enabled": body.enabled, "issuer": body.issuer, "client_id": body.client_id,
               "has_secret": bool(secret)}, **audit_ctx(request))
    await pdb.commit()
    return {"data": {"ok": True}}

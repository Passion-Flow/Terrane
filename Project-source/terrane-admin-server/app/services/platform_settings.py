"""Platform settings repository (terrane_main: system_settings + branding single row).

system_settings: generic key-value pairs (wizard state / email / login / password policy ...),
scope='global'.
branding: deployment-level white-label single row (SINGLETON_ID); returns factory defaults when
missing (page-based zero-config rule).
All writes are committed by the caller (orchestrated in the same transaction as audit).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.platform.branding import SINGLETON_ID, Branding
from app.models.platform.system_setting import SystemSetting

WIZARD_KEY = "wizard"
EMAIL_KEY = "email"
SECURITY_KEY = "security"


async def get_security_policy(db: AsyncSession) -> dict[str, int]:
    """Security policy (password rules, etc.) — system_settings['security'] overrides the
    factory config defaults.

    All password validation points in both the frontend and admin read this uniformly; the
    deployer changes it in one place under the admin "Settings → Security" and it takes effect
    platform-wide (page-based zero-config).
    """
    cfg = get_settings()
    stored = await get_setting(db, SECURITY_KEY) or {}
    return {
        "password_min_length": int(stored.get("password_min_length", cfg.password_min_length)),
        "password_require_char_classes": int(
            stored.get("password_require_char_classes", cfg.password_require_char_classes)),
        "login_lock_threshold": int(stored.get("login_lock_threshold", cfg.login_lock_threshold)),
        "login_lock_seconds": int(stored.get("login_lock_seconds", cfg.login_lock_seconds)),
        "session_absolute_ttl_seconds": int(
            stored.get("session_absolute_ttl_seconds", cfg.session_absolute_ttl_seconds)),
    }


async def get_setting(db: AsyncSession, key: str, *, scope: str = "global",
                      scope_id: str = "") -> dict[str, Any] | None:
    stmt = select(SystemSetting).where(
        SystemSetting.key == key, SystemSetting.scope == scope,
        SystemSetting.scope_id == scope_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    return dict(row.value) if row else None


async def set_setting(db: AsyncSession, key: str, value: dict[str, Any], *,
                      scope: str = "global", scope_id: str = "") -> None:
    """upsert (overwrites on uq(key,scope,scope_id))."""
    stmt = select(SystemSetting).where(
        SystemSetting.key == key, SystemSetting.scope == scope,
        SystemSetting.scope_id == scope_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, scope=scope, scope_id=scope_id, value=value))


async def get_branding(db: AsyncSession) -> Branding:
    """Read the white-label single row; create and return a factory-default row when missing."""
    row = await db.get(Branding, SINGLETON_ID)
    if row is None:
        row = Branding(id=SINGLETON_ID)
        db.add(row)
        await db.flush()
    return row

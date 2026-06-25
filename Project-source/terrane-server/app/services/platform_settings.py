"""Platform DB settings reads (terrane_main: system_settings) — the frontend reads email config, etc.

Email config is written by the admin initialization wizard (key='email' scope='global'); the frontend reads it to send verification/reset emails.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.system_setting import SystemSetting

EMAIL_KEY = "email"
SECURITY_KEY = "security"


async def get_setting(db: AsyncSession, key: str, *, scope: str = "global",
                      scope_id: str = "") -> dict[str, Any] | None:
    stmt = select(SystemSetting).where(
        SystemSetting.key == key, SystemSetting.scope == scope,
        SystemSetting.scope_id == scope_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    return dict(row.value) if row else None


async def get_security_policy(db: AsyncSession) -> dict[str, int]:
    """Security policy (password rules) — system_settings['security'] overrides the factory config defaults.

    Changing it once under Admin "Settings -> Security" takes effect across frontend registration/reset/password-change (same platform DB terrane_main as the admin side).
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

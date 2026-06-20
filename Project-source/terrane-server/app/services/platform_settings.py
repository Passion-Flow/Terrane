"""平台库设置读取（terrane_main：system_settings）— 前台读邮件配置等。

邮件配置由后台初始化向导写入（key='email' scope='global'）；前台读取用于发验证/重置邮件。
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
    """安全策略（密码规则）—— system_settings['security'] 覆盖于出厂 config 默认之上。

    后台「设置→安全」改一处，前台注册/重置/改密同步生效（与后台同一平台库 terrane_main）。
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

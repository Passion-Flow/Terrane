"""平台库设置仓（terrane_main：system_settings + branding 单行）。

system_settings：通用键值（向导状态/邮件/登录/密码策略…），scope='global'。
branding：部署级白标单行（SINGLETON_ID），缺失时返回出厂默认（页面化零配置铁律）。
所有写入由调用方 commit（与 audit 同事务编排）。
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
    """安全策略（密码规则等）—— system_settings['security'] 覆盖于出厂 config 默认之上。

    前后台所有口令校验点统一读此，部署方在后台「设置→安全」改一处全平台生效（页面化零配置）。
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
    """upsert（按 uq(key,scope,scope_id) 覆盖）。"""
    stmt = select(SystemSetting).where(
        SystemSetting.key == key, SystemSetting.scope == scope,
        SystemSetting.scope_id == scope_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, scope=scope, scope_id=scope_id, value=value))


async def get_branding(db: AsyncSession) -> Branding:
    """读白标单行；缺失时创建出厂默认行并返回。"""
    row = await db.get(Branding, SINGLETON_ID)
    if row is None:
        row = Branding(id=SINGLETON_ID)
        db.add(row)
        await db.flush()
    return row

"""初始化向导状态机（PRD 4.12.1：License→超管→邮件→Branding→完成）。

步骤完成态来源：
  license     —— 由 License gate 保证（能到达本接口即已激活）→ 恒 done。
  super_admin —— 当前超管 must_change_password=False（首登改密完成）。
  email       —— system_settings['email'].configured 或向导标记 email_done。
  branding    —— 向导标记 branding_done（branding 有出厂默认，确认/跳过即 done）。
completed —— system_settings['wizard'].completed（POST /wizard/complete 置位）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.email_presets import all_presets
from app.services.platform_settings import EMAIL_KEY, WIZARD_KEY, get_branding, get_setting

STEPS = ("license", "super_admin", "email", "branding")


def _mask_email(cfg: dict[str, Any]) -> dict[str, Any]:
    """脱敏邮件配置（绝不回传密码明文）。"""
    return {
        "host": cfg.get("host", ""),
        "port": cfg.get("port", 465),
        "encryption": cfg.get("encryption", "auto"),
        "username": cfg.get("username", ""),
        "from_address": cfg.get("from_address", ""),
        "from_name": cfg.get("from_name", "Terrane"),
        "allow_insecure": bool(cfg.get("allow_insecure", False)),
        "has_password": bool(cfg.get("password")),
    }


async def get_state(db: AsyncSession, *, super_admin_done: bool) -> dict[str, Any]:
    """汇总向导状态（license 步由 gate 保证，恒 done）。"""
    wiz = await get_setting(db, WIZARD_KEY) or {}
    email_cfg = await get_setting(db, EMAIL_KEY) or {}
    branding = await get_branding(db)

    done = {
        "license": True,
        "super_admin": super_admin_done,
        "email": bool(email_cfg.get("configured")) or bool(wiz.get("email_done")),
        "branding": bool(wiz.get("branding_done")),
    }
    steps: list[dict[str, str]] = []
    current_set = False
    for key in STEPS:
        if done[key]:
            status = "done"
        elif not current_set:
            status, current_set = "current", True
        else:
            status = "pending"
        steps.append({"key": key, "status": status})

    return {
        "completed": bool(wiz.get("completed")),
        "steps": steps,
        "email": {"configured": done["email"], **_mask_email(email_cfg)},
        "branding": {
            "product_name": branding.product_name,
            "logo_data": branding.logo_data,
            "accent_color": branding.accent_color,
            "login_subtitle": branding.login_subtitle,
            "support_url": branding.support_url,
            "enabled": branding.enabled,
        },
        "email_presets": all_presets(),
    }

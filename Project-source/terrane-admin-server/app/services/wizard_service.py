"""Setup wizard state machine (PRD 4.12.1: License -> Super admin -> Email -> Branding -> Done).

Sources of each step's completion state:
  license     —— Guaranteed by the License gate (reaching this endpoint means it is already activated) -> always done.
  super_admin —— The current super admin has must_change_password=False (the first-login password change is complete).
  email       —— system_settings['email'].configured, or the wizard flag email_done.
  branding    —— The wizard flag branding_done (branding has a factory default; confirming/skipping marks it done).
completed —— system_settings['wizard'].completed (set by POST /wizard/complete).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.email_presets import all_presets
from app.services.platform_settings import EMAIL_KEY, WIZARD_KEY, get_branding, get_setting

STEPS = ("license", "super_admin", "email", "branding")


def _mask_email(cfg: dict[str, Any]) -> dict[str, Any]:
    """Redact the email configuration (never return the plaintext password)."""
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
    """Aggregate the wizard state (the license step is guaranteed by the gate, always done)."""
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

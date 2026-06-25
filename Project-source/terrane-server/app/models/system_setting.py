"""SystemSetting (generic key-value setting) ORM — platform DB terrane_main (02-database entity #36).

A general-purpose config store: email / object storage / login policy / password policy / data retention /
wizard state, etc. value=JSONB (sensitive fields are ciphertext + an __enc marker); uq(key, scope, scope_id);
upsert overwrites, auditing goes through audit_logs.
"""

from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, HardTimestampMixin, JSONType, UUIDMixin


class SystemSetting(UUIDMixin, HardTimestampMixin, Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="global")
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    value: Mapped[dict] = mapped_column(JSONType, nullable=False)

    __table_args__ = (
        UniqueConstraint("key", "scope", "scope_id", name="uq_system_settings_key_scope"),
    )

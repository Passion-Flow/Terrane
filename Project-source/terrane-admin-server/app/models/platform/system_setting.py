"""SystemSetting（平台库 terrane_main：system_settings）— ORM 映射拷贝。

schema 权威在 terrane-server/app/models/system_setting.py + 迁移 000002。admin 仅读写。
"""

from __future__ import annotations

import uuid

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.platform import JSONType, PlatformBase, PlatformTimestampMixin


class SystemSetting(PlatformTimestampMixin, PlatformBase):
    __tablename__ = "system_settings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="global")
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    value: Mapped[dict] = mapped_column(JSONType, nullable=False)

    __table_args__ = (
        UniqueConstraint("key", "scope", "scope_id", name="uq_system_settings_key_scope"),
    )

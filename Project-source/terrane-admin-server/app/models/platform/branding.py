"""Branding（平台库 terrane_main：branding 单行）— ORM 映射拷贝。

schema 权威在 terrane-server/app/models/branding.py + 迁移 000002。admin（初始化向导）写入。
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.platform import PlatformBase, PlatformTimestampMixin

# 单例行固定主键（与 terrane-server 一致）。
SINGLETON_ID = uuid.UUID("00000000-0000-0000-0000-0000000b5a0d")


class Branding(PlatformTimestampMixin, PlatformBase):
    __tablename__ = "branding"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    product_name: Mapped[str] = mapped_column(String(120), nullable=False, default="Terrane")
    logo_data: Mapped[str | None] = mapped_column(Text, nullable=True)   # 控制台/工作区 Logo
    login_logo: Mapped[str | None] = mapped_column(Text, nullable=True)  # 登录页 Logo
    favicon: Mapped[str | None] = mapped_column(Text, nullable=True)     # 站点 favicon
    accent_color: Mapped[str] = mapped_column(String(16), nullable=False, default="#0f9b8e")
    login_subtitle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    support_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

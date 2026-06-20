"""Branding（部署级白标）ORM — 平台库 terrane_main（02-database：B 端基线配置）。

全局单行（id 固定 SINGLETON_ID）：产品名 / Logo / 主题色 / 登录副标 / 支持链接。
初始化向导「Branding」步写入；前后台读取应用白标。出厂自带默认值（页面化零配置铁律）。
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, HardTimestampMixin, UUIDMixin

# 单例行固定主键（全局唯一一行白标配置）。
SINGLETON_ID = uuid.UUID("00000000-0000-0000-0000-0000000b5a0d")


class Branding(UUIDMixin, HardTimestampMixin, Base):
    __tablename__ = "branding"

    product_name: Mapped[str] = mapped_column(String(120), nullable=False, default="Terrane")
    logo_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # 控制台/工作区 Logo（data URI 或 URL）
    login_logo: Mapped[str | None] = mapped_column(Text, nullable=True)  # 登录页 Logo
    favicon: Mapped[str | None] = mapped_column(Text, nullable=True)     # 站点 favicon
    accent_color: Mapped[str] = mapped_column(String(16), nullable=False, default="#0f9b8e")
    login_subtitle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    support_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

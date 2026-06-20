"""SystemSetting（通用键值设置）ORM — 平台库 terrane_main（02-database 实体 #36）。

通用配置仓：邮件 / 对象存储 / 登录策略 / 密码策略 / 数据保留 / 向导状态等。
value=JSONB（敏感字段密文 + __enc 标记）；uq(key, scope, scope_id)；upsert 覆盖，审计走 audit_logs。
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

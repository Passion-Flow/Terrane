"""权限注册表 — 中央 P.* 常量（阶段②认证地基所需最小集，阶段③业务模块扩充）。

命名：<domain>.<resource>.<action>，小写、点分、单数资源。
业务代码只引用 P.* 常量，禁裸权限字符串。
"""

from __future__ import annotations


class P:
    # platform.license.*（后台 License 区）
    LICENSE_READ = "platform.license.read"
    LICENSE_UPDATE = "platform.license.update"

    # platform.user.*（后台操作员管理）
    USER_READ = "platform.user.read"
    USER_WRITE = "platform.user.write"
    USER_DELETE = "platform.user.delete"

    # platform.audit.*
    AUDIT_READ = "platform.audit.read"
    AUDIT_EXPORT = "platform.audit.export"

    # system.*（设置 / 初始化向导）
    SETTINGS_READ = "system.settings.read"
    SETTINGS_WRITE = "system.settings.write"

    # platform.workspace.*（租户工作区管理）
    WORKSPACE_READ = "platform.workspace.read"
    WORKSPACE_WRITE = "platform.workspace.write"

    # platform.seat.*（席位/成员管理）
    SEAT_READ = "platform.seat.read"
    SEAT_WRITE = "platform.seat.write"

    # platform.channel.*（模型渠道：六路收口 + web-search）
    CHANNEL_READ = "platform.channel.read"
    CHANNEL_WRITE = "platform.channel.write"

    # platform.connector.*（连接器凭据 vault）
    CONNECTOR_READ = "platform.connector.read"
    CONNECTOR_WRITE = "platform.connector.write"

    # platform.quota.*（配额三类型）/ platform.budget.*（token 月预算闸门）
    QUOTA_READ = "platform.quota.read"
    QUOTA_WRITE = "platform.quota.write"
    BUDGET_READ = "platform.budget.read"
    BUDGET_WRITE = "platform.budget.write"

    # platform.ingest.*（全局摄入队列监控）
    INGEST_MONITOR = "platform.ingest.monitor"

    # platform.backup.*（备份状态可视）
    BACKUP_READ = "platform.backup.read"

    # platform.integration.*（Webhooks / Data Push / OTel）
    INTEGRATION_READ = "platform.integration.read"
    INTEGRATION_WRITE = "platform.integration.write"


ALL_PERMISSIONS: set[str] = {
    v for k, v in vars(P).items() if not k.startswith("_") and isinstance(v, str)
}

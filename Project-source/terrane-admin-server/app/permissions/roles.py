"""角色 → 权限映射。3 角色模型：super_admin / admin / auditor（.agent.md [角色权限]）。"""

from __future__ import annotations

from app.permissions.registry import ALL_PERMISSIONS, P

# super_admin 持通配；admin/auditor 显式枚举。
PLATFORM_ROLES: dict[str, set[str]] = {
    "super_admin": {"*"},
    "admin": {  # = Platform Admin
        P.LICENSE_READ, P.LICENSE_UPDATE,
        P.USER_READ,
        P.SETTINGS_READ, P.SETTINGS_WRITE,
        # 租户运营：工作区 / 席位 / 配额 / 预算。
        P.WORKSPACE_READ, P.WORKSPACE_WRITE,
        P.SEAT_READ, P.SEAT_WRITE,
        P.QUOTA_READ, P.QUOTA_WRITE,
        P.BUDGET_READ, P.BUDGET_WRITE,
        # 模型渠道 / 连接器凭据 / 摄入监控 / 备份。
        P.CHANNEL_READ, P.CHANNEL_WRITE,
        P.CONNECTOR_READ, P.CONNECTOR_WRITE,
        P.INGEST_MONITOR,
        P.BACKUP_READ,
        # 集成（Webhooks / Data Push）。
        P.INTEGRATION_READ, P.INTEGRATION_WRITE,
        # NOT：操作员增删 / 审计
    },
    "auditor": {
        P.AUDIT_READ, P.AUDIT_EXPORT,
        P.LICENSE_READ,   # 只读 License 状态
        P.BACKUP_READ,    # 只读备份状态
    },
}


def role_has(role: str, permission: str) -> bool:
    perms = PLATFORM_ROLES.get(role, set())
    return "*" in perms or permission in perms


def assert_registry_consistent() -> None:
    """启动自检：roles 中列出的权限必须在 registry 中存在。"""
    for role, perms in PLATFORM_ROLES.items():
        for perm in perms:
            if perm != "*" and perm not in ALL_PERMISSIONS:
                raise RuntimeError(f"role '{role}' references unregistered permission '{perm}'")

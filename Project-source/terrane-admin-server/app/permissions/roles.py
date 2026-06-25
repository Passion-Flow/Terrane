"""Role → permission mapping. 3-role model: super_admin / admin / auditor (.agent.md [role permissions])."""

from __future__ import annotations

from app.permissions.registry import ALL_PERMISSIONS, P

# super_admin holds the wildcard; admin/auditor are enumerated explicitly.
PLATFORM_ROLES: dict[str, set[str]] = {
    "super_admin": {"*"},
    "admin": {  # = Platform Admin
        P.LICENSE_READ, P.LICENSE_UPDATE,
        P.USER_READ,
        P.SETTINGS_READ, P.SETTINGS_WRITE,
        # Tenant operations: workspaces / seats / quotas / budgets.
        P.WORKSPACE_READ, P.WORKSPACE_WRITE,
        P.SEAT_READ, P.SEAT_WRITE,
        P.QUOTA_READ, P.QUOTA_WRITE,
        P.BUDGET_READ, P.BUDGET_WRITE,
        # Model channels / connector credentials / ingest monitoring / backup.
        P.CHANNEL_READ, P.CHANNEL_WRITE,
        P.CONNECTOR_READ, P.CONNECTOR_WRITE,
        P.INGEST_MONITOR,
        P.BACKUP_READ,
        # Integrations (Webhooks / Data Push).
        P.INTEGRATION_READ, P.INTEGRATION_WRITE,
        # NOT: operator create/delete / audit
    },
    "auditor": {
        P.AUDIT_READ, P.AUDIT_EXPORT,
        P.LICENSE_READ,   # read-only License status
        P.BACKUP_READ,    # read-only backup status
    },
}


def role_has(role: str, permission: str) -> bool:
    perms = PLATFORM_ROLES.get(role, set())
    return "*" in perms or permission in perms


def assert_registry_consistent() -> None:
    """Startup self-check: every permission listed in roles must exist in the registry."""
    for role, perms in PLATFORM_ROLES.items():
        for perm in perms:
            if perm != "*" and perm not in ALL_PERMISSIONS:
                raise RuntimeError(f"role '{role}' references unregistered permission '{perm}'")

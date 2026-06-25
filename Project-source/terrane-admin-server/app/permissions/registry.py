"""Permission registry — central P.* constants (minimal set required by the Stage 2 auth foundation, expanded by Stage 3 business modules).

Naming: <domain>.<resource>.<action>, lowercase, dot-separated, singular resource.
Business code references only P.* constants, no bare permission strings.
"""

from __future__ import annotations


class P:
    # platform.license.* (admin License area)
    LICENSE_READ = "platform.license.read"
    LICENSE_UPDATE = "platform.license.update"

    # platform.user.* (admin operator management)
    USER_READ = "platform.user.read"
    USER_WRITE = "platform.user.write"
    USER_DELETE = "platform.user.delete"

    # platform.audit.*
    AUDIT_READ = "platform.audit.read"
    AUDIT_EXPORT = "platform.audit.export"

    # system.* (settings / setup wizard)
    SETTINGS_READ = "system.settings.read"
    SETTINGS_WRITE = "system.settings.write"

    # platform.workspace.* (tenant workspace management)
    WORKSPACE_READ = "platform.workspace.read"
    WORKSPACE_WRITE = "platform.workspace.write"

    # platform.seat.* (seat/member management)
    SEAT_READ = "platform.seat.read"
    SEAT_WRITE = "platform.seat.write"

    # platform.channel.* (model channels: six-way consolidation + web-search)
    CHANNEL_READ = "platform.channel.read"
    CHANNEL_WRITE = "platform.channel.write"

    # platform.connector.* (connector credential vault)
    CONNECTOR_READ = "platform.connector.read"
    CONNECTOR_WRITE = "platform.connector.write"

    # platform.quota.* (three quota types) / platform.budget.* (monthly token budget gate)
    QUOTA_READ = "platform.quota.read"
    QUOTA_WRITE = "platform.quota.write"
    BUDGET_READ = "platform.budget.read"
    BUDGET_WRITE = "platform.budget.write"

    # platform.ingest.* (global ingest queue monitoring)
    INGEST_MONITOR = "platform.ingest.monitor"

    # platform.backup.* (backup status visibility)
    BACKUP_READ = "platform.backup.read"

    # platform.integration.* (Webhooks / Data Push / OTel)
    INTEGRATION_READ = "platform.integration.read"
    INTEGRATION_WRITE = "platform.integration.write"


ALL_PERMISSIONS: set[str] = {
    v for k, v in vars(P).items() if not k.startswith("_") and isinstance(v, str)
}

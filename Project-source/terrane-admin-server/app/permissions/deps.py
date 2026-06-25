"""@require_perm dependency factory. The backend is authoritative — never trust the frontend session snapshot, fall back to the role mapping for validation."""

from __future__ import annotations

from fastapi import Depends

from app.api.deps import CurrentUser, get_current_user
from app.core.errors import BizError
from app.permissions.roles import role_has


def require_perm(permission: str):
    """Return a dependency that validates `permission` against the current operator's role."""

    async def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if "*" in user.permissions or permission in user.permissions:
            return user
        # Defense in depth: beyond the session snapshot, validate once more against the authoritative role mapping.
        if role_has(user.role, permission):
            return user
        raise BizError("PERM_DENIED", {"required": permission})

    return _checker

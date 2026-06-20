"""@require_perm 依赖工厂。后端权威——绝不信任前端 session 快照，再按角色映射兜底校验。"""

from __future__ import annotations

from fastapi import Depends

from app.api.deps import CurrentUser, get_current_user
from app.core.errors import BizError
from app.permissions.roles import role_has


def require_perm(permission: str):
    """返回一个依赖，对当前操作员角色校验 `permission`。"""

    async def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if "*" in user.permissions or permission in user.permissions:
            return user
        # 纵深防御：除 session 快照外，再按权威角色映射校验一次。
        if role_has(user.role, permission):
            return user
        raise BizError("PERM_DENIED", {"required": permission})

    return _checker

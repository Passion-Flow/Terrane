"""License 锁定态网关（多点防绕过的第 1 点；第 2 点为路由级 require_license 依赖）。

锁定态行为（licensing.md）：拒绝一切受保护接口，统一 403 + `LICENSE_REQUIRED`；
仅放行健康探针与 License 状态只读接口（前台无激活能力，激活在后台管理端）。
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.licensing.state import LicenseState

ALLOWED_PREFIXES: tuple[str, ...] = (
    "/livez",
    "/readyz",
    "/healthz",
    "/metrics",  # 可观测：监控在锁定态也应可抓
    "/api/v1/license/status",
    "/api/v1/branding",  # 公开品牌：前台锁定/登录页在认证前即需展示部署方白标
)


def _request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


class LicenseGateMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, state: LicenseState) -> None:  # noqa: ANN001 — starlette 签名
        super().__init__(app)
        self._state = state

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        request.state.request_id = request.headers.get("X-Request-Id") or _request_id()
        if not self._state.unlocked and not request.url.path.startswith(ALLOWED_PREFIXES):
            return JSONResponse(
                status_code=403,
                content={
                    "code": "LICENSE_REQUIRED",
                    "message": "License activation required.",
                    "details": {},
                    "request_id": request.state.request_id,
                },
                headers={"X-Request-Id": request.state.request_id},
            )
        response = await call_next(request)
        response.headers.setdefault("X-Request-Id", request.state.request_id)
        return response


def require_license(request: Request) -> None:
    """路由级二次校验（业务路由必须挂载本依赖 — 抗单点 patch 绕过）。"""
    state: LicenseState = request.app.state.license
    if not state.unlocked:
        raise HTTPException(
            status_code=403,
            detail={"code": "LICENSE_REQUIRED", "message": "License activation required."},
        )

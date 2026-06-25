"""License locked-state gateway (point 1 of multi-point bypass protection; point 2 is the route-level require_license dependency).

Locked-state behavior (licensing.md): reject all protected endpoints with a uniform 403 + `LICENSE_REQUIRED`;
only allow health probes and read-only License status endpoints (the frontend has no activation capability; activation happens in the admin backend).
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
    "/admin-api/v1/license",
    "/admin-api/v1/branding",  # public branding: the login/activation page must show the deployer's white-label before authentication
)


def _request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


class LicenseGateMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, state: LicenseState) -> None:  # noqa: ANN001 — starlette signature
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
    """Route-level secondary check (business routes must mount this dependency — resistant to single-point patch bypass)."""
    state: LicenseState = request.app.state.license
    if not state.unlocked:
        raise HTTPException(
            status_code=403,
            detail={"code": "LICENSE_REQUIRED", "message": "License activation required."},
        )

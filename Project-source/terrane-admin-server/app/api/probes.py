"""Health probes (observability.md: three probes) — whitelisted under License lockdown
(operations must still be able to probe liveness while locked down).

- /livez   process liveness (UP as soon as it starts)
- /readyz  readiness: the first License signature verification has completed (install_id written to the shared volume)
- /healthz aggregate
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

router = APIRouter(tags=["probes"])


@router.get("/livez")
async def livez() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    state = request.app.state.license
    ready = bool(getattr(state, "initial_checked", False))
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "starting"},
    )


@router.get("/healthz")
async def healthz(request: Request) -> dict:
    state = request.app.state.license
    return {"status": "ok", "license_status": state.verdict.status}

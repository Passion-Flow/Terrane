"""健康探针（observability.md：三探针）—— License 锁定态白名单内（运维需在锁定态也能探活）。

- /livez  进程存活（启动即 UP）
- /readyz  就绪：License 首次验签已完成（install_id 已写入共享卷）
- /healthz  聚合
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

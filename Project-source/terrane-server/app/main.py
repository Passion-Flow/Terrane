"""terrane-api application factory — Phase 1: License gating (development-discipline phasing).

Phase 1 scope: License lock state + read-only frontend status + probes only.
Authentication and business modules are wired in during later phases.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1 import assistant as assistant_api
from app.api.v1 import auth as auth_api
from app.api.v1 import branding as branding_api
from app.api.v1 import external as external_api
from app.api.v1 import knowledge_bases as kb_api
from app.api.v1 import license as license_api
from app.api.v1 import mcp as mcp_api
from app.api.v1 import memories as memories_api
from app.api.v1 import models as models_api
from app.api.v1 import sso as sso_api
from app.api.v1 import probes
from app.core.config import get_settings
from app.core.errors import BizError
from app.core.logging import configure_logging
from app.licensing.state import LicenseState
from app.middlewares.license_gate import LicenseGateMiddleware
from app.observability import MetricsMiddleware, render_metrics

log = structlog.get_logger("terrane.app")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    state: LicenseState = app.state.license
    await state.start()
    yield
    await state.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.terrane_log_level)
    app = FastAPI(title="Terrane Console API", version="1.0.0",
                  lifespan=_lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.license = LicenseState(settings)
    app.add_middleware(LicenseGateMiddleware, state=app.state.license)
    app.add_middleware(MetricsMiddleware)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(render_metrics(), media_type="text/plain; version=0.0.4")

    app.include_router(probes.router)
    app.include_router(license_api.router)
    app.include_router(branding_api.router)  # Public branding (no login / available while locked; used for frontend logo/title/login page)
    app.include_router(auth_api.router)  # Phase 2: frontend user authentication (register/login/verify/reset)
    app.include_router(kb_api.router)  # Phase 4: knowledge base CRUD (platform database terrane_main)
    app.include_router(mcp_api.router)  # MCP Server: knowledge bases exposed as MCP tools (Bearer auth)
    app.include_router(external_api.router)  # External Knowledge API: integration for external apps such as Dify/Coze/n8n (Bearer auth)
    app.include_router(memories_api.router)  # Memory system: per-user memory (extraction/recall)
    app.include_router(models_api.router)  # Available models: frontend "Model Settings" dropdown (synced with backend channels)
    app.include_router(assistant_api.router)  # Personal AI assistant: cross-database retrieval + memory + persisted conversations
    app.include_router(sso_api.router)  # SSO: OIDC enterprise login (authorization code flow)

    @app.exception_handler(BizError)
    async def biz_error_handler(request: Request, exc: BizError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "")
        return JSONResponse(status_code=exc.http_status, content=exc.envelope(request_id))

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "")
        detail = exc.detail if isinstance(exc.detail, dict) else {
            "code": "SYSTEM_HTTP_ERROR", "message": str(exc.detail)}
        return JSONResponse(
            status_code=exc.status_code,
            content={**detail, "details": detail.get("details", {}), "request_id": request_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request,
                                           exc: RequestValidationError) -> JSONResponse:
        # Unified error envelope (error-codes.md) — does not expose FastAPI's default {"detail": [...]} structure.
        request_id = getattr(request.state, "request_id", "")
        fields = [{"field": ".".join(str(p) for p in err.get("loc", [])[1:]),
                   "type": err.get("type", "")} for err in exc.errors()]
        return JSONResponse(status_code=400, content={
            "code": "VALIDATION_FAILED", "message": "Request validation failed.",
            "details": {"fields": fields}, "request_id": request_id})

    return app


app = create_app()

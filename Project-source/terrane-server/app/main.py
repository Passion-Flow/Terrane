"""terrane-api 应用工厂 — 阶段①：License gating（development-discipline 阶段顺序）。

阶段①边界：仅 License 锁定态 + 前台状态只读 + 探针。认证/业务模块在后续阶段接入。
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
    app.include_router(branding_api.router)  # 公开品牌（免登录/锁定态可取，前台 Logo/标题/登录页用）
    app.include_router(auth_api.router)  # 阶段②：前台用户认证（register/login/verify/reset）
    app.include_router(kb_api.router)  # 阶段④：知识库 CRUD（平台库 terrane_main）
    app.include_router(mcp_api.router)  # MCP Server：知识库暴露为 MCP 工具（Bearer 鉴权）
    app.include_router(external_api.router)  # External Knowledge API：Dify/Coze/n8n 等外部应用接入（Bearer 鉴权）
    app.include_router(memories_api.router)  # 记忆系统：per-user 记忆（抽取/唤回）
    app.include_router(models_api.router)  # 可用模型：前台「模型设置」下拉选（同步后台渠道）
    app.include_router(assistant_api.router)  # 个人 AI 助手：跨库检索+记忆+持久化对话
    app.include_router(sso_api.router)  # SSO：OIDC 企业登录（授权码流）

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
        # 统一错误信封（error-codes.md）—— 不暴露 FastAPI 默认 {"detail": [...]} 结构。
        request_id = getattr(request.state, "request_id", "")
        fields = [{"field": ".".join(str(p) for p in err.get("loc", [])[1:]),
                   "type": err.get("type", "")} for err in exc.errors()]
        return JSONResponse(status_code=400, content={
            "code": "VALIDATION_FAILED", "message": "Request validation failed.",
            "details": {"fields": fields}, "request_id": request_id})

    return app


app = create_app()

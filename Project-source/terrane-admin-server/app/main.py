"""terrane-admin-api 应用工厂 — 阶段①：License gating（后台 = 激活写入方）。"""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse

from app.api import probes
from app.api.admin_v1 import audit_logs as audit_logs_api
from app.api.admin_v1 import auth as auth_api
from app.api.admin_v1 import branding as branding_api
from app.api.admin_v1 import channels as channels_api
from app.api.admin_v1 import knowledge_bases as kb_overview_api
from app.api.admin_v1 import license as license_api
from app.api.admin_v1 import members as members_api
from app.api.admin_v1 import operators as operators_api
from app.api.admin_v1 import settings as settings_api
from app.api.admin_v1 import workspaces as workspaces_api
from app.api.admin_v1 import wizard as wizard_api
from app.core.config import get_settings
from app.core.errors import BizError
from app.core.logging import configure_logging
from app.licensing.state import LicenseState
from app.middlewares.license_gate import LicenseGateMiddleware
from app.permissions.roles import assert_registry_consistent

log = structlog.get_logger("terrane.admin.app")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    state: LicenseState = app.state.license
    await state.start()
    yield
    await state.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.terrane_log_level)
    assert_registry_consistent()  # 启动自检：角色引用的权限必须已注册
    app = FastAPI(title="Terrane Admin API", version="1.0.0",
                  lifespan=_lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.license = LicenseState(settings)
    app.add_middleware(LicenseGateMiddleware, state=app.state.license)

    app.include_router(probes.router)
    app.include_router(license_api.router)
    app.include_router(branding_api.router)  # 公开品牌（免登录/锁定态可取，登录页/侧边栏用）
    app.include_router(auth_api.router)  # 阶段②：后台认证（login/logout/me）
    app.include_router(wizard_api.router)  # 阶段②：初始化向导（平台库 terrane_main）
    app.include_router(audit_logs_api.router)  # 阶段②：审计日志查询（平台库 terrane_main）
    app.include_router(workspaces_api.router)  # 阶段②：工作区列表（平台库 terrane_main）
    app.include_router(members_api.router)  # 阶段②：成员/前台用户列表（平台库 terrane_main）
    app.include_router(operators_api.router)  # 阶段②：后台操作员管理（管理库 terrane_admin）
    app.include_router(settings_api.router)  # 阶段②：后台设置（邮件/品牌，平台库 terrane_main）
    app.include_router(channels_api.router)  # 阶段③：模型渠道（管理库 terrane_admin）
    app.include_router(kb_overview_api.router)  # 阶段④：后台库总览（平台俯视,只读元数据）

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
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request,
                                           exc: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "")
        fields = [{"field": ".".join(str(p) for p in err.get("loc", [])[1:]),
                   "type": err.get("type", "")} for err in exc.errors()]
        return JSONResponse(status_code=400, content={
            "code": "VALIDATION_FAILED", "message": "Request validation failed.",
            "details": {"fields": fields}, "request_id": request_id})

    return app


app = create_app()

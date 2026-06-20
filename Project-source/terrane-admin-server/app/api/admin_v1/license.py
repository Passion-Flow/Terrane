"""后台 License 区 — 状态卡 + 粘贴激活（licensing.md：锁定态例外路径）。

阶段①边界：产品已激活（unlocked）时替换 License 需要超管权限，认证体系在阶段②落地，
故本阶段对"已激活后再次激活"一律 403 AUTH_REQUIRED（fail-closed，不开放无鉴权替换）。
审计事件本阶段走结构化日志，阶段②接入 audit_logs 表（同事务）。
"""

from __future__ import annotations

import asyncio
import datetime
import time
import uuid
from collections import deque
from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.errors import BizError
from app.licensing.state import METHOD_OFFLINE, METHOD_ONLINE, LicenseState
from app.licensing.store import write_envelope
from app.permissions.registry import P

log = structlog.get_logger("terrane.admin.license")
router = APIRouter(prefix="/admin-api/v1/license", tags=["license"])

_VERDICT_ERROR_CODES = {
    "invalid_signature": "LICENSE_INVALID_SIGNATURE",
    "binding_mismatch": "LICENSE_BINDING_MISMATCH",
    "expired": "LICENSE_EXPIRED",
    "revoked": "LICENSE_REVOKED",
    "locked": "LICENSE_INVALID",
}


class ActivateRequest(BaseModel):
    method: str = Field(pattern=f"^({METHOD_OFFLINE}|{METHOD_ONLINE})$")
    credential: str = Field(min_length=8, max_length=65536)


class _RateLimiter:
    """激活接口每 IP 滑动窗口限频（单实例后台足够；防爆破签名/短码）。"""

    def __init__(self, limit_per_minute: int) -> None:
        self._limit = limit_per_minute
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        window = self._hits.setdefault(key, deque())
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self._limit:
            return False
        window.append(now)
        return True


_limiter: _RateLimiter | None = None


def _rate_limit(request: Request) -> None:
    global _limiter
    if _limiter is None:
        _limiter = _RateLimiter(get_settings().terrane_activate_rate_limit_per_minute)
    client_ip = request.client.host if request.client else "unknown"
    if not _limiter.allow(client_ip):
        raise HTTPException(status_code=429, detail={
            "code": "RATE_LIMIT_EXCEEDED", "message": "Too many activation attempts.",
        }, headers={"Retry-After": "60"})


def _mask(value: str | None) -> str | None:
    if not value:
        return None
    return f"{value[:4]}****{value[-4:]}" if len(value) > 8 else "****"


def _days_left(active_until: str | None) -> int | None:
    if not active_until:
        return None
    try:
        until = datetime.datetime.fromisoformat(active_until.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (until - datetime.datetime.now(datetime.timezone.utc)).days


def _issued_from_id(license_id: str | None) -> str | None:
    """active_from 兜底:license_id 是 uuid7,前 48 位为创建毫秒时间戳 → 反解作生效时间。

    在线租约(edge lease)只带 active_until 不带 active_from,但 license_id 恒在且稳定,
    其 uuid7 时间戳即该证签发/生效时刻,据此保证「生效时间」绝不为空。
    """
    if not license_id:
        return None
    try:
        ms = uuid.UUID(license_id).int >> 80  # uuid7 高 48 位 = unix 毫秒
    except (ValueError, AttributeError):
        return None
    if ms <= 0:
        return None
    return datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc).isoformat()


def _card(state: LicenseState) -> dict:
    verdict, payload = state.verdict, state.verdict.payload or {}
    return {
        "status": verdict.status,
        "unlocked": verdict.unlocked,
        "fingerprint": state.fingerprint,          # 激活页显著展示的部署/集群 ID
        "license_id_masked": _mask(payload.get("license_id")),
        "cluster_id_masked": _mask(payload.get("cluster_id")),
        "customer": payload.get("customer"),
        "product": payload.get("product"),
        "subscription": payload.get("subscription"),
        "active_from": payload.get("active_from") or _issued_from_id(payload.get("license_id")),
        "active_until": payload.get("active_until"),
        "days_left": _days_left(payload.get("active_until")),
        "quotas": payload.get("quotas"),
        "features": payload.get("features"),
        "mode": payload.get("mode"),
        "binding": payload.get("binding"),
        "alg": payload.get("alg"),
    }


def _activate(request: Request, method: str, credential: str, *, authorized: bool = False) -> dict:
    _rate_limit(request)
    state: LicenseState = request.app.state.license
    if state.unlocked and not authorized:
        # 已激活后的替换需要超管鉴权（locked 态免登激活;已激活态须超管）。
        raise HTTPException(status_code=403, detail={
            "code": "AUTH_REQUIRED",
            "message": "Replacing an active license requires super admin authentication.",
        })
    settings = get_settings()
    verdict = state.try_credential(method, credential)
    if not verdict.unlocked:
        code = _VERDICT_ERROR_CODES.get(verdict.status, "LICENSE_INVALID")
        log.warning("license.activate_rejected", status=verdict.status, reason=verdict.reason)
        raise HTTPException(status_code=422, detail={
            "code": code, "message": "License verification failed.",
            "details": {"status": verdict.status},
        })
    write_envelope(Path(settings.terrane_license_path), method, credential)
    state.verify_now()
    log.info("license.activated", method=method, status=state.verdict.status,
             license_id_masked=_mask((state.verdict.payload or {}).get("license_id")))
    return {"data": _card(state), "request_id": request.state.request_id}


@router.get("")
async def license_card(request: Request) -> dict:
    state = request.app.state.license
    # 节流重验：锁定态 ≤4s（激活近即时反映，不每次轮询都打 edge——防限流/死循环）；
    # active 态 ≤8s（吊销近即时反映）。串行锁已保证不并发重入。
    await asyncio.to_thread(state.verify_if_stale, 4.0 if not state.unlocked else 8.0)
    return {"data": _card(state), "request_id": request.state.request_id}


@router.post("/activate")
async def activate(request: Request, body: ActivateRequest) -> dict:
    state: LicenseState = request.app.state.license
    authorized = False
    if state.unlocked:
        # 已激活态替换 → 须超管会话（locked 态不要求,反死锁）。
        try:
            user = await get_current_user(request)
        except BizError:
            user = None
        authorized = bool(user and (user.role == "super_admin"
                                    or "*" in user.permissions
                                    or P.LICENSE_UPDATE in user.permissions))
    return _activate(request, body.method, body.credential.strip(), authorized=authorized)

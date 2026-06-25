"""Admin License section — status card + paste-to-activate (licensing.md: locked-state exception path).

Stage 1 boundary: once the product is activated (unlocked), replacing the License requires super admin permission, but the auth system only lands in stage 2,
so in this stage any "re-activation after already activated" returns 403 AUTH_REQUIRED (fail-closed; unauthenticated replacement is not opened up).
Audit events go to structured logs in this stage; stage 2 wires in the audit_logs table (same transaction).
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
    """Per-IP sliding-window rate limit for the activation endpoint (sufficient for a single-instance admin; guards against brute-forcing signatures/short codes)."""

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
    """active_from fallback: license_id is a uuid7 whose top 48 bits are the creation timestamp in ms -> decode it as the effective time.

    An online lease (edge lease) carries only active_until, not active_from, but license_id is always present and stable,
    and its uuid7 timestamp is exactly the issue/effective moment of that license, which guarantees the "effective time" is never empty.
    """
    if not license_id:
        return None
    try:
        ms = uuid.UUID(license_id).int >> 80  # uuid7 top 48 bits = unix milliseconds
    except (ValueError, AttributeError):
        return None
    if ms <= 0:
        return None
    return datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc).isoformat()


def _card(state: LicenseState) -> dict:
    verdict, payload = state.verdict, state.verdict.payload or {}
    return {
        "required": state.required,                # open-source build: false -> frontend hides activation/badge, guard passes through
        "status": verdict.status,
        "unlocked": verdict.unlocked,
        "fingerprint": state.fingerprint,          # deployment/cluster ID prominently shown on the activation page
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
        # Replacement after activation requires super admin auth (locked state allows login-free activation; activated state requires super admin).
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
    # Throttled re-verification: locked state <=4s (activation reflects near-instantly, without hitting edge on every poll -- avoids rate limiting / tight loops);
    # active state <=8s (revocation reflects near-instantly). The serial lock already prevents concurrent re-entry.
    await asyncio.to_thread(state.verify_if_stale, 4.0 if not state.unlocked else 8.0)
    return {"data": _card(state), "request_id": request.state.request_id}


@router.post("/activate")
async def activate(request: Request, body: ActivateRequest) -> dict:
    state: LicenseState = request.app.state.license
    authorized = False
    if state.unlocked:
        # Replacement in the activated state -> requires a super admin session (not required in the locked state, to avoid a deadlock).
        try:
            user = await get_current_user(request)
        except BizError:
            user = None
        authorized = bool(user and (user.role == "super_admin"
                                    or "*" in user.permissions
                                    or P.LICENSE_UPDATE in user.permissions))
    return _activate(request, body.method, body.credential.strip(), authorized=authorized)

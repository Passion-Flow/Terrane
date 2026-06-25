"""Frontend License area — status read-only (licensing.md: locked-state exception path; the frontend has no activation capability).

The frontend lock page polls this endpoint (locked 3s / active 8s): activation reflects near-instantly, revocation locks within ≤8s.
The activation action lives only in the admin console (terrane-admin-api).
"""

from __future__ import annotations

import asyncio
import datetime

from fastapi import APIRouter, Request

from app.licensing.state import LicenseState

router = APIRouter(prefix="/api/v1/license", tags=["license"])


def _days_left(active_until: str | None) -> int | None:
    if not active_until:
        return None
    try:
        until = datetime.datetime.fromisoformat(active_until.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (until - datetime.datetime.now(datetime.timezone.utc)).days


@router.get("/status")
async def license_status(request: Request) -> dict:
    state: LicenseState = request.app.state.license
    # Throttled re-verification: locked state ≤4s (activation reflects near-instantly, but not every poll hits the edge — prevents rate-limiting/infinite loops);
    # active state ≤8s (revocation reflects near-instantly). A serial lock already prevents concurrent re-entry.
    await asyncio.to_thread(state.verify_if_stale, 4.0 if not state.unlocked else 8.0)
    verdict, payload = state.verdict, state.verdict.payload or {}
    active_until = payload.get("active_until")
    return {
        "data": {
            "required": state.required,  # false in the open-source edition → frontend hides activation/badges and guards let through
            "status": verdict.status,
            "unlocked": verdict.unlocked,
            "active_until": active_until,
            "days_left": _days_left(active_until),
        },
        "request_id": request.state.request_id,
    }

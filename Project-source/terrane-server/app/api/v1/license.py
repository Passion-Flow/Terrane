"""前台 License 区 — 状态只读（licensing.md：锁定态例外路径，前台无激活能力）。

前台锁定页轮询此端点（锁定 3s / 激活 8s）：激活近即时反映、吊销 ≤8s 锁定。
激活动作仅在后台管理端（terrane-admin-api）。
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
    # 节流重验：锁定态 ≤4s（激活近即时反映，但不每次轮询都打 edge——防限流/死循环）；
    # active 态 ≤8s（吊销近即时反映）。串行锁已保证不并发重入。
    await asyncio.to_thread(state.verify_if_stale, 4.0 if not state.unlocked else 8.0)
    verdict, payload = state.verdict, state.verdict.payload or {}
    active_until = payload.get("active_until")
    return {
        "data": {
            "status": verdict.status,
            "unlocked": verdict.unlocked,
            "active_until": active_until,
            "days_left": _days_left(active_until),
        },
        "request_id": request.state.request_id,
    }

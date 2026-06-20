"""轻量可观测(零依赖,Prometheus 文本格式,可被 Prometheus 直接抓取)。

请求计数中间件(按 method+status)+ 时延累计 + in-flight gauge。/metrics 暴露。
低基数:只按 method/status 标签,不按路径(避免 ID 爆炸)。OTel trace 后续按需接。
"""

from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_counts: dict[tuple[str, int], int] = defaultdict(int)
_dur_sum: float = 0.0
_inflight: int = 0


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        global _dur_sum, _inflight
        _inflight += 1
        start = time.perf_counter()
        status = 500
        try:
            resp = await call_next(request)
            status = resp.status_code
            return resp
        finally:
            _inflight -= 1
            _dur_sum += time.perf_counter() - start
            _counts[(request.method, status)] += 1


def render_metrics() -> str:
    out = [
        "# HELP terrane_requests_total Total HTTP requests.",
        "# TYPE terrane_requests_total counter",
    ]
    for (method, status), c in sorted(_counts.items()):
        out.append(f'terrane_requests_total{{method="{method}",status="{status}"}} {c}')
    out += [
        "# HELP terrane_request_duration_seconds_sum Cumulative request duration.",
        "# TYPE terrane_request_duration_seconds_sum counter",
        f"terrane_request_duration_seconds_sum {_dur_sum:.6f}",
        "# HELP terrane_requests_inflight In-flight requests.",
        "# TYPE terrane_requests_inflight gauge",
        f"terrane_requests_inflight {_inflight}",
    ]
    return "\n".join(out) + "\n"

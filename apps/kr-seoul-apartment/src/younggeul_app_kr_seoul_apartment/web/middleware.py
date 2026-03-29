from __future__ import annotations

import re
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from younggeul_app_kr_seoul_apartment.simulation.metrics import (
    CounterLike,
    HistogramLike,
    get_meter,
    metric_attrs,
)


_UUID_PATH_SEGMENT_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
)

_web_requests_total: CounterLike | None = None
_web_request_duration_seconds: HistogramLike | None = None


def web_requests_total() -> CounterLike:
    global _web_requests_total
    if _web_requests_total is None:
        _web_requests_total = get_meter().create_counter(
            "web_requests_total",
            description="Total number of web requests",
            unit="{request}",
        )
    return _web_requests_total


def web_request_duration_seconds() -> HistogramLike:
    global _web_request_duration_seconds
    if _web_request_duration_seconds is None:
        _web_request_duration_seconds = get_meter().create_histogram(
            "web_request_duration_seconds",
            description="Duration of web requests",
            unit="s",
        )
    return _web_request_duration_seconds


def _normalize_path(path: str) -> str:
    return _UUID_PATH_SEGMENT_RE.sub(":id", path)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        method = request.method
        path = _normalize_path(request.url.path)
        status_code = "500"

        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            return response
        finally:
            web_requests_total().add(
                1,
                attributes=metric_attrs(method=method, path=path, status_code=status_code),
            )
            web_request_duration_seconds().record(
                time.perf_counter() - start,
                attributes=metric_attrs(method=method, path=path),
            )

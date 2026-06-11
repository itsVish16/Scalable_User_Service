import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.routing import Match

from app.core.metrics import ACTIVE_REQUESTS, REQUEST_COUNT, REQUEST_LATENCY

SKIP_PATH_PREFIXES = ("/health", "/metrics")


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = self._get_route_template(request)

        if path.startswith(SKIP_PATH_PREFIXES):
            return await call_next(request)

        start_time = time.perf_counter()
        ACTIVE_REQUESTS.labels(method=request.method).inc()
        try:
            response = await call_next(request)
        finally:
            ACTIVE_REQUESTS.labels(method=request.method).dec()
        duration = time.perf_counter() - start_time

        REQUEST_COUNT.labels(
            method=request.method,
            path=path,
            status_code=str(response.status_code),
        ).inc()

        REQUEST_LATENCY.labels(
            method=request.method,
            path=path,
        ).observe(duration)

        return response

    @staticmethod
    def _get_route_template(request: Request) -> str:
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                return getattr(route, "path", request.url.path)
        return "unknown"

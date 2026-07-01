import time
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

HTTP_REQUESTS = Counter(
    "earth_http_requests_total",
    "HTTP requests processed by the Earth Monitoring API",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "earth_http_request_duration_seconds",
    "HTTP request duration for the Earth Monitoring API",
    ("method", "route"),
)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)
        started = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        HTTP_REQUESTS.labels(request.method, route_path, str(response.status_code)).inc()
        HTTP_DURATION.labels(request.method, route_path).observe(time.perf_counter() - started)
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))[:128]
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{time.perf_counter() - started:.4f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self)"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; base-uri 'none'"
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, max_body_bytes: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.max_body_bytes = max_body_bytes

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                too_large = int(content_length) > self.max_body_bytes
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
            if too_large:
                return JSONResponse(status_code=413, content={"detail": "Request body too large"})
        return await call_next(request)


class LocalRateLimitMiddleware(BaseHTTPMiddleware):
    """A bounded, single-process safety limit; production ingress should enforce a shared limit."""

    def __init__(self, app: object, requests_per_minute: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.limit = requests_per_minute
        self.requests: defaultdict[str, deque[float]] = defaultdict(deque)
        self.last_cleanup = time.monotonic()

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in {"/health/live", "/health/ready"}:
            return await call_next(request)
        now = time.monotonic()
        if now - self.last_cleanup >= 60:
            stale_before = now - 60
            for client, requests in list(self.requests.items()):
                while requests and requests[0] <= stale_before:
                    requests.popleft()
                if not requests:
                    del self.requests[client]
            self.last_cleanup = now
        key = request.client.host if request.client else "unknown"
        bucket = self.requests[key]
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": "60"},
            )
        bucket.append(now)
        return await call_next(request)

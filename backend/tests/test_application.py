from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app
from app.middleware import LocalRateLimitMiddleware, RequestSizeLimitMiddleware


def test_liveness_and_request_context_headers() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live", headers={"X-Request-ID": "test-request"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == "test-request"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Security-Policy"] == "frame-ancestors 'none'; base-uri 'none'"
    assert float(response.headers["X-Process-Time"]) >= 0


def test_openapi_contains_core_product_routes() -> None:
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/v1/auth/token" in paths
    assert "/api/v1/events/geojson" in paths
    assert "/api/v1/events/{event_id}/review" in paths
    assert "/api/v1/monitoring/runs" in paths
    assert "/api/v1/planet/satellites" in paths
    assert "/api/v1/planet/earthquakes" in paths
    assert "/api/v1/assistant/query" in paths


def test_prometheus_metrics_are_exposed() -> None:
    with TestClient(app) as client:
        client.get("/health/live")
        response = client.get("/metrics")
    assert response.status_code == 200
    assert "earth_http_requests_total" in response.text


def test_local_rate_limit_rejects_excess_requests() -> None:
    limited_app = FastAPI()
    limited_app.add_middleware(LocalRateLimitMiddleware, requests_per_minute=1)

    @limited_app.get("/resource")
    async def resource() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(limited_app) as client:
        first = client.get("/resource")
        second = client.get("/resource")
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["Retry-After"] == "60"


def test_request_size_limit_rejects_large_declared_body() -> None:
    limited_app = FastAPI()
    limited_app.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=4)

    @limited_app.post("/resource")
    async def resource() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(limited_app) as client:
        response = client.post("/resource", content="12345")
    assert response.status_code == 413

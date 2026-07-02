from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import (
    assistant,
    auth,
    dashboard,
    events,
    monitoring,
    planetary,
    projects,
    reports,
    solar_system,
)
from app.core.config import get_settings
from app.core.database import Base, SessionFactory, engine
from app.middleware import (
    LocalRateLimitMiddleware,
    MetricsMiddleware,
    RequestContextMiddleware,
    RequestSizeLimitMiddleware,
)
from app.seed import bootstrap_local_workspace

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings.assert_safe_for_production()
    if settings.database_url.startswith("sqlite"):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await bootstrap_local_workspace()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Auditable Earth-observation monitoring API. Detections include source provenance, "
        "model identity, confidence, geometry, and review state."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=settings.max_request_body_bytes)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(LocalRateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

for router in (
    auth.router,
    projects.router,
    events.router,
    monitoring.router,
    planetary.router,
    solar_system.router,
    dashboard.router,
    assistant.router,
    reports.router,
):
    app.include_router(router, prefix=settings.api_prefix)


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness() -> dict[str, Any]:
    async with SessionFactory() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ready", "database": "connected", "version": app.version}


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

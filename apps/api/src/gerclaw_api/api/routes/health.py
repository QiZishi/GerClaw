"""Liveness, readiness, and Prometheus endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from gerclaw_api.auth import AuthContext, require_metrics_read
from gerclaw_api.metrics import render_metrics
from gerclaw_api.services.health_service import DependencyHealthService
from gerclaw_api.services.rate_limit import RateLimiter

router = APIRouter(tags=["operations"])


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Report that the ASGI process can serve requests."""

    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(request: Request) -> Response:
    """Report whether every mandatory dependency is currently usable."""

    health_service: DependencyHealthService = request.app.state.health_service
    report = await health_service.check()
    status_code = (
        status.HTTP_200_OK if report["status"] == "ready" else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(report, status_code=status_code)


@router.get("/metrics", include_in_schema=False)
async def metrics(
    request: Request,
    identity: Annotated[AuthContext, Depends(require_metrics_read)],
) -> Response:
    """Expose low-cardinality process metrics for Prometheus scraping."""

    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(tenant_id=identity.tenant_id, actor_id=identity.actor_id)
    body, media_type = render_metrics()
    return Response(body, media_type=media_type)

"""Process and dependency health endpoints."""

import logging

from elasticsearch import ApiError, TransportError
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_session_factory
from app.schemas.health import LiveResponse, ReadyResponse

LOGGER = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "/live",
    response_model=LiveResponse,
    summary="Check process liveness",
    description="Reports whether the API process can serve requests without checking dependencies.",
)
async def live() -> LiveResponse:
    """Return process liveness without making dependency calls."""
    return LiveResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyResponse}},
    summary="Check dependency readiness",
    description="Checks PostgreSQL and Elasticsearch availability.",
)
async def ready(request: Request) -> JSONResponse:
    """Return readiness and a safe status for each required dependency."""
    components = {
        "postgresql": await _postgresql_ready(),
        "elasticsearch": await _elasticsearch_ready(request),
    }
    is_ready = all(component == "ok" for component in components.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ok" if is_ready else "unavailable", "components": components},
    )


async def _postgresql_ready() -> str:
    try:
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        LOGGER.warning("PostgreSQL readiness check failed", exc_info=True)
        return "unavailable"
    return "ok"


async def _elasticsearch_ready(request: Request) -> str:
    try:
        is_available = await request.app.state.elasticsearch.ping()
    except (ApiError, TransportError):
        LOGGER.warning("Elasticsearch readiness check failed", exc_info=True)
        return "unavailable"
    return "ok" if is_available else "unavailable"

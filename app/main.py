import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers.documents import router as documents_router
from app.api.routers.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_engine
from app.search.client import create_elasticsearch_client

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application resources."""
    app.state.elasticsearch = create_elasticsearch_client(get_settings())
    LOGGER.info("Application started")
    try:
        yield
    finally:
        await app.state.elasticsearch.close()
        await dispose_engine()
        LOGGER.info("Application stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    app = FastAPI(
        title=settings.app_name,
        description="Search PostgreSQL-backed documents through Elasticsearch.",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/", tags=["system"])
    async def root() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(health_router)
    app.include_router(documents_router)
    return app


app = create_app()

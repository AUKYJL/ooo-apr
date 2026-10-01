from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from elasticsearch import AsyncElasticsearch
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Document
from app.db.session import dispose_engine, get_session_factory
from app.main import create_app
from app.search.index import DocumentIndex


@pytest_asyncio.fixture
async def elasticsearch_index_name() -> AsyncIterator[str]:
    """Provide an index that cannot overlap with seeded application data."""
    yield f"test-documents-{uuid4().hex}"


@pytest_asyncio.fixture(autouse=True)
async def isolated_stores(
    monkeypatch: pytest.MonkeyPatch, elasticsearch_index_name: str
) -> AsyncIterator[None]:
    """Reset the dedicated test database and Elasticsearch index for each test."""
    monkeypatch.setenv("ELASTICSEARCH_INDEX", elasticsearch_index_name)
    get_settings.cache_clear()
    settings = get_settings()
    client = AsyncElasticsearch(settings.elasticsearch_url)
    index = DocumentIndex(client, settings.elasticsearch_index)
    await index.recreate()
    async with get_session_factory()() as session:
        await session.execute(delete(Document))
        await session.commit()
    try:
        yield
    finally:
        await client.indices.delete(index=settings.elasticsearch_index, ignore_unavailable=True)
        await client.close()
        await dispose_engine()
        get_settings.cache_clear()


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as database_session:
        yield database_session


@pytest_asyncio.fixture
async def document_index() -> AsyncIterator[DocumentIndex]:
    settings = get_settings()
    client = AsyncElasticsearch(settings.elasticsearch_url)
    try:
        yield DocumentIndex(client, settings.elasticsearch_index)
    finally:
        await client.close()


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.state.elasticsearch = AsyncElasticsearch(get_settings().elasticsearch_url)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await app.state.elasticsearch.close()
    await dispose_engine()

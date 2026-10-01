from datetime import datetime

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.api.routers import health
from app.api.routers.documents import get_document_service
from app.db.models import Document
from app.main import create_app
from app.services.documents import DeleteDependencyError, DocumentNotFoundError, DocumentService


class FakeDocumentIndex:
    async def search_ids(self, query: str) -> list[int]:
        assert query == "новость"
        return [2, 1]


class FakeScalarResult:
    def all(self) -> list[Document]:
        return [
            Document(id=1, rubrics=["old"], text="database old", created_date=datetime(2024, 1, 1)),
            Document(id=2, rubrics=["new"], text="database new", created_date=datetime(2024, 2, 1)),
        ]


class FakeSession:
    async def scalars(self, statement: object) -> FakeScalarResult:
        return FakeScalarResult()


class FakeDeleteService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.deleted_id: int | None = None

    async def delete(self, document_id: int) -> None:
        self.deleted_id = document_id
        if self.error:
            raise self.error


class FakeHealthSession:
    async def execute(self, statement: object) -> None:
        return None


class FakeHealthSessionContext:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def __aenter__(self) -> FakeHealthSession:
        if self.error:
            raise self.error
        return FakeHealthSession()

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeElasticsearch:
    def __init__(self, available: bool) -> None:
        self.available = available

    async def ping(self) -> bool:
        return self.available


@pytest.mark.asyncio
async def test_root_responds() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_live_does_not_need_dependencies() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_reports_dependency_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        health,
        "get_session_factory",
        lambda: lambda: FakeHealthSessionContext(),
    )
    app = create_app()
    app.state.elasticsearch = FakeElasticsearch(available=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "components": {"postgresql": "ok", "elasticsearch": "unavailable"},
    }


@pytest.mark.asyncio
async def test_ready_reports_postgresql_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        health,
        "get_session_factory",
        lambda: lambda: FakeHealthSessionContext(SQLAlchemyError("unavailable")),
    )
    app = create_app()
    app.state.elasticsearch = FakeElasticsearch(available=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["components"]["postgresql"] == "unavailable"


@pytest.mark.asyncio
async def test_search_rejects_whitespace_only_query() -> None:
    app = create_app()
    app.dependency_overrides[get_document_service] = lambda: None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/documents/search", params={"q": "   "})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_rejects_query_longer_than_1000_characters() -> None:
    app = create_app()
    app.dependency_overrides[get_document_service] = lambda: None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/documents/search", params={"q": "x" * 1001})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_returns_hydrated_documents_in_search_order() -> None:
    app = create_app()
    app.dependency_overrides[get_document_service] = lambda: DocumentService(
        FakeSession(),  # type: ignore[arg-type]
        FakeDocumentIndex(),  # type: ignore[arg-type]
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/documents/search", params={"q": " новость "})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 2,
            "rubrics": ["new"],
            "text": "database new",
            "created_date": "2024-02-01T00:00:00",
        },
        {
            "id": 1,
            "rubrics": ["old"],
            "text": "database old",
            "created_date": "2024-01-01T00:00:00",
        },
    ]


@pytest.mark.asyncio
async def test_delete_returns_empty_204_response() -> None:
    app = create_app()
    service = FakeDeleteService()
    app.dependency_overrides[get_document_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/v1/documents/42")

    assert response.status_code == 204
    assert response.content == b""
    assert service.deleted_id == 42


@pytest.mark.asyncio
async def test_delete_maps_missing_document_to_404() -> None:
    app = create_app()
    app.dependency_overrides[get_document_service] = lambda: FakeDeleteService(
        DocumentNotFoundError()
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/v1/documents/42")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_maps_dependency_failure_to_503() -> None:
    app = create_app()
    app.dependency_overrides[get_document_service] = lambda: FakeDeleteService(
        DeleteDependencyError()
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/v1/documents/42")

    assert response.status_code == 503

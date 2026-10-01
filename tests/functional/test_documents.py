from datetime import datetime, timedelta

import httpx
import pytest
from elasticsearch import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Document
from app.search.index import DocumentIndex, IndexDocument


async def add_documents(
    session: AsyncSession, document_index: DocumentIndex, count: int = 25
) -> list[Document]:
    documents = [
        Document(
            rubrics=[f"rubric-{number}"],
            text="важная интеграционная новость",
            created_date=datetime(2024, 1, 1) + timedelta(days=number),
        )
        for number in range(count)
    ]
    session.add_all(documents)
    await session.commit()
    await document_index.bulk_index(
        IndexDocument(document.id, document.text, document.created_date) for document in documents
    )
    return documents


@pytest.mark.asyncio
async def test_search_returns_authoritative_fields_newest_first_and_limits_to_twenty(
    api_client: httpx.AsyncClient, session: AsyncSession, document_index: DocumentIndex
) -> None:
    documents = await add_documents(session, document_index)

    response = await api_client.get("/api/v1/documents/search", params={"q": "новость"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 20
    assert [item["id"] for item in payload] == [document.id for document in documents[-1:-21:-1]]
    assert payload[0] == {
        "id": documents[-1].id,
        "rubrics": ["rubric-24"],
        "text": "важная интеграционная новость",
        "created_date": "2024-01-25T00:00:00",
    }


@pytest.mark.asyncio
async def test_search_returns_empty_list_and_validates_query(
    api_client: httpx.AsyncClient,
) -> None:
    empty = await api_client.get("/api/v1/documents/search", params={"q": "несуществующее"})
    whitespace = await api_client.get("/api/v1/documents/search", params={"q": "   "})

    assert empty.status_code == 200
    assert empty.json() == []
    assert whitespace.status_code == 422


@pytest.mark.asyncio
async def test_delete_removes_document_from_postgresql_and_elasticsearch(
    api_client: httpx.AsyncClient,
    session: AsyncSession,
    document_index: DocumentIndex,
) -> None:
    document = (await add_documents(session, document_index, count=1))[0]
    document_id = document.id

    response = await api_client.delete(f"/api/v1/documents/{document_id}")

    assert response.status_code == 204
    session.expire_all()
    assert await session.get(Document, document_id) is None
    with pytest.raises(NotFoundError):
        await document_index._client.get(index=document_index._name, id=str(document_id))


@pytest.mark.asyncio
async def test_delete_missing_document_returns_404(api_client: httpx.AsyncClient) -> None:
    response = await api_client.delete("/api/v1/documents/999999")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ready_reports_live_dependencies(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "components": {"postgresql": "ok", "elasticsearch": "ok"},
    }


@pytest.mark.asyncio
async def test_functional_test_index_is_unique_and_not_the_application_index(
    elasticsearch_index_name: str,
) -> None:
    assert get_settings().elasticsearch_index == elasticsearch_index_name
    assert elasticsearch_index_name.startswith("test-documents-")
    assert elasticsearch_index_name != "documents"

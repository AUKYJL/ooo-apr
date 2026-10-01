from datetime import datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from elasticsearch import AsyncElasticsearch

from app.core.config import get_settings
from app.search.index import DocumentIndex, IndexDocument


class FakeIndices:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []

    async def exists(self, *, index: str) -> bool:
        return False

    async def create(self, **kwargs: object) -> None:
        self.created.append(kwargs)


class FakeCluster:
    def __init__(self) -> None:
        self.health_calls: list[dict[str, object]] = []

    async def health(self, **kwargs: object) -> dict[str, bool]:
        self.health_calls.append(kwargs)
        return {"timed_out": False}


class FakeElasticsearchClient:
    def __init__(self) -> None:
        self.indices = FakeIndices()
        self.cluster = FakeCluster()


@pytest_asyncio.fixture
async def document_index() -> DocumentIndex:
    client = AsyncElasticsearch(get_settings().elasticsearch_url)
    if not await client.ping():
        await client.close()
        pytest.skip("Elasticsearch is not available")

    index = DocumentIndex(client, f"test-documents-{uuid4().hex}")
    try:
        yield index
    finally:
        await client.indices.delete(index=index._name, ignore_unavailable=True)
        await client.close()


@pytest.mark.asyncio
async def test_index_mapping_bulk_search_and_delete(document_index: DocumentIndex) -> None:
    assert await document_index.ensure_exists()
    assert not await document_index.ensure_exists()
    mapping = await document_index._client.indices.get_mapping(index=document_index._name)
    index_mapping = mapping[document_index._name]["mappings"]
    assert index_mapping["dynamic"] == "strict"
    assert index_mapping["properties"]["text"]["analyzer"] == "russian"

    assert await document_index.bulk_index(
        [
            IndexDocument(1, "важная новость", datetime(2024, 1, 1)),
            IndexDocument(2, "важная новость", datetime(2024, 3, 1)),
            IndexDocument(3, "важная новость", datetime(2024, 2, 1)),
        ]
    ) == 3
    assert await document_index.search_ids("новость") == [2, 3, 1]
    assert await document_index.delete(2)
    assert await document_index.search_ids("новость") == [3, 1]


@pytest.mark.asyncio
async def test_index_creation_waits_for_primary_shard() -> None:
    client = FakeElasticsearchClient()
    document_index = DocumentIndex(client, "test-documents-isolated")  # type: ignore[arg-type]

    assert await document_index.ensure_exists()
    assert client.indices.created == [
        {
            "index": "test-documents-isolated",
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "id": {"type": "long"},
                    "text": {"type": "text", "analyzer": "russian"},
                    "created_date": {"type": "date"},
                },
            },
        }
    ]
    assert client.cluster.health_calls == [
        {
            "index": "test-documents-isolated",
            "wait_for_status": "yellow",
            "timeout": "30s",
        }
    ]

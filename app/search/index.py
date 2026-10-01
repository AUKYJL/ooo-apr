from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from elasticsearch import AsyncElasticsearch, NotFoundError
from elasticsearch.helpers import async_bulk

DOCUMENT_INDEX_MAPPING: Final[dict[str, object]] = {
    "mappings": {
        "dynamic": "strict",
        "properties": {
            "id": {"type": "long"},
            "text": {"type": "text", "analyzer": "russian"},
            "created_date": {"type": "date"},
        },
    },
}


@dataclass(frozen=True, slots=True)
class IndexDocument:
    """The fields stored in the Elasticsearch document projection."""

    id: int
    text: str
    created_date: datetime


class DocumentIndex:
    """Explicit operations for the document Elasticsearch projection."""

    def __init__(self, client: AsyncElasticsearch, name: str) -> None:
        self._client = client
        self._name = name

    async def ensure_exists(self) -> bool:
        """Create the index when absent and report whether it was created."""
        if await self._client.indices.exists(index=self._name):
            return False
        await self._client.indices.create(
            index=self._name,
            mappings=DOCUMENT_INDEX_MAPPING["mappings"],
        )
        await self._wait_until_ready()
        return True

    async def recreate(self) -> None:
        """Replace the index for an explicit seed/reset workflow."""
        if await self._client.indices.exists(index=self._name):
            await self._client.indices.delete(index=self._name)
        await self._client.indices.create(
            index=self._name,
            mappings=DOCUMENT_INDEX_MAPPING["mappings"],
        )
        await self._wait_until_ready()

    async def _wait_until_ready(self) -> None:
        """Wait until the new index has an active primary shard."""
        response = await self._client.cluster.health(
            index=self._name,
            wait_for_status="yellow",
            timeout="30s",
        )
        if response["timed_out"]:
            raise RuntimeError(f"Elasticsearch index {self._name!r} did not become ready")

    async def bulk_index(self, documents: Iterable[IndexDocument]) -> int:
        """Index document projections in one asynchronous bulk operation."""
        actions = (
            {
                "_op_type": "index",
                "_index": self._name,
                "_id": str(document.id),
                "_source": {
                    "id": document.id,
                    "text": document.text,
                    "created_date": document.created_date,
                },
            }
            for document in documents
        )
        success_count, _ = await async_bulk(self._client, actions, refresh="wait_for")
        return success_count

    async def search_ids(self, query: str) -> list[int]:
        """Return up to twenty matching IDs in the required stable search order."""
        if not query.strip():
            raise ValueError("query must not be empty")

        response = await self._client.search(
            index=self._name,
            query={"match": {"text": query}},
            sort=[
                {"created_date": {"order": "desc"}},
                {"_score": {"order": "desc"}},
                {"id": {"order": "asc"}},
            ],
            size=20,
            track_scores=True,
        )
        return [int(hit["_source"]["id"]) for hit in response["hits"]["hits"]]

    async def delete(self, document_id: int) -> bool:
        """Delete a document projection by its PostgreSQL ID."""
        try:
            response = await self._client.delete(
                index=self._name,
                id=str(document_id),
                refresh="wait_for",
            )
        except NotFoundError:
            return False
        return response["result"] == "deleted"

    async def ping(self) -> bool:
        """Report whether Elasticsearch is reachable."""
        return await self._client.ping()

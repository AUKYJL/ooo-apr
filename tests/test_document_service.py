from datetime import datetime

import pytest
from elastic_transport import ConnectionError

from app.db.models import Document
from app.services.documents import DeleteDependencyError, DocumentNotFoundError, DocumentService


class FakeDocumentIndex:
    async def search_ids(self, query: str) -> list[int]:
        assert query == "новость"
        return [3, 1, 2]


class FakeScalarResult:
    def __init__(self, documents: list[Document]) -> None:
        self._documents = documents

    def all(self) -> list[Document]:
        return self._documents


class FakeSession:
    async def scalars(self, statement: object) -> FakeScalarResult:
        return FakeScalarResult(
            [
                Document(id=1, rubrics=["one"], text="first", created_date=datetime(2024, 1, 1)),
                Document(id=3, rubrics=["three"], text="third", created_date=datetime(2024, 1, 3)),
            ]
        )


class DeleteSession:
    def __init__(self, document: Document | None) -> None:
        self.document = document
        self.deleted: Document | None = None
        self.committed = False

    async def get(self, model: type[Document], document_id: int) -> Document | None:
        assert model is Document
        assert self.document is None or document_id == self.document.id
        return self.document

    async def delete(self, document: Document) -> None:
        self.deleted = document

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        pass


class DeleteIndex:
    def __init__(self, result: bool = True, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.deleted_id: int | None = None

    async def delete(self, document_id: int) -> bool:
        self.deleted_id = document_id
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_search_hydrates_and_restores_elasticsearch_order() -> None:
    service = DocumentService(FakeSession(), FakeDocumentIndex())  # type: ignore[arg-type]

    documents = await service.search("новость")

    assert [document.id for document in documents] == [3, 1]
    assert [document.text for document in documents] == ["third", "first"]


@pytest.mark.asyncio
async def test_delete_removes_index_before_authoritative_document() -> None:
    document = Document(id=7, rubrics=["one"], text="text", created_date=datetime(2024, 1, 1))
    session = DeleteSession(document)
    index = DeleteIndex()
    service = DocumentService(session, index)  # type: ignore[arg-type]

    await service.delete(7)

    assert index.deleted_id == 7
    assert session.deleted is document
    assert session.committed


@pytest.mark.asyncio
async def test_delete_missing_database_document_does_not_call_elasticsearch() -> None:
    index = DeleteIndex()
    service = DocumentService(DeleteSession(None), index)  # type: ignore[arg-type]

    with pytest.raises(DocumentNotFoundError):
        await service.delete(7)

    assert index.deleted_id is None


@pytest.mark.asyncio
async def test_delete_tolerates_missing_elasticsearch_projection() -> None:
    document = Document(id=7, rubrics=["one"], text="text", created_date=datetime(2024, 1, 1))
    session = DeleteSession(document)
    service = DocumentService(session, DeleteIndex(result=False))  # type: ignore[arg-type]

    await service.delete(7)

    assert session.deleted is document
    assert session.committed


@pytest.mark.asyncio
async def test_delete_elasticsearch_failure_preserves_database_document() -> None:
    document = Document(id=7, rubrics=["one"], text="text", created_date=datetime(2024, 1, 1))
    session = DeleteSession(document)
    service = DocumentService(
        session,
        DeleteIndex(error=ConnectionError("Elasticsearch unavailable")),  # type: ignore[arg-type]
    )

    with pytest.raises(DeleteDependencyError):
        await service.delete(7)

    assert session.deleted is None
    assert not session.committed

import logging

from elasticsearch import ApiError, TransportError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.search.index import DocumentIndex

LOGGER = logging.getLogger(__name__)


class SearchDependencyError(RuntimeError):
    """Raised when search or authoritative document storage is unavailable."""


class DocumentNotFoundError(RuntimeError):
    """Raised when an authoritative document does not exist."""


class DeleteDependencyError(RuntimeError):
    """Raised when a document cannot be deleted from a dependency."""


class DocumentService:
    """Coordinate Elasticsearch discovery with PostgreSQL document hydration."""

    def __init__(self, session: AsyncSession, document_index: DocumentIndex) -> None:
        self._session = session
        self._document_index = document_index

    async def search(self, query: str) -> list[Document]:
        """Return authoritative documents in the Elasticsearch result order."""
        try:
            document_ids = await self._document_index.search_ids(query)
        except (ApiError, TransportError) as error:
            LOGGER.warning("Elasticsearch search failed", exc_info=error)
            raise SearchDependencyError("Elasticsearch is unavailable") from error

        if not document_ids:
            return []

        try:
            statement = select(Document).where(Document.id.in_(document_ids))
            documents = (await self._session.scalars(statement)).all()
        except SQLAlchemyError as error:
            LOGGER.warning("PostgreSQL document hydration failed", exc_info=error)
            raise SearchDependencyError("PostgreSQL is unavailable") from error

        documents_by_id = {document.id: document for document in documents}
        ordered_documents = []
        for document_id in document_ids:
            document = documents_by_id.get(document_id)
            if document is None:
                LOGGER.warning("Indexed document %d is missing from PostgreSQL", document_id)
                continue
            ordered_documents.append(document)
        return ordered_documents

    async def delete(self, document_id: int) -> None:
        """Delete a document projection, then its authoritative row."""
        try:
            document = await self._session.get(Document, document_id)
        except SQLAlchemyError as error:
            LOGGER.warning("PostgreSQL document lookup failed", exc_info=error)
            raise DeleteDependencyError("PostgreSQL is unavailable") from error

        if document is None:
            raise DocumentNotFoundError(f"Document {document_id} was not found")

        try:
            deleted = await self._document_index.delete(document_id)
        except (ApiError, TransportError) as error:
            LOGGER.warning("Elasticsearch document deletion failed", exc_info=error)
            raise DeleteDependencyError("Elasticsearch is unavailable") from error

        if not deleted:
            LOGGER.warning("Document %d is missing from Elasticsearch", document_id)

        try:
            await self._session.delete(document)
            await self._session.commit()
        except SQLAlchemyError as error:
            await self._session.rollback()
            LOGGER.warning("PostgreSQL document deletion failed", exc_info=error)
            raise DeleteDependencyError("PostgreSQL is unavailable") from error

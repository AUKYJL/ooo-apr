from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.schemas.documents import DocumentResponse
from app.search.index import DocumentIndex
from app.services.documents import (
    DeleteDependencyError,
    DocumentNotFoundError,
    DocumentService,
    SearchDependencyError,
)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


async def normalize_query(
    q: Annotated[str, Query(min_length=1, max_length=1000)],
) -> str:
    """Trim a supplied query and reject values containing only whitespace."""
    query = q.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="q must contain non-whitespace characters",
        )
    return query


async def get_document_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentService:
    """Build a request-scoped search service."""
    document_index = DocumentIndex(
        request.app.state.elasticsearch,
        get_settings().elasticsearch_index,
    )
    return DocumentService(session, document_index)


@router.get(
    "/search",
    response_model=list[DocumentResponse],
    summary="Search documents",
    description="Searches indexed document text and returns PostgreSQL-authoritative fields.",
)
async def search_documents(
    query: Annotated[str, Depends(normalize_query)],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> list[DocumentResponse]:
    """Search indexed text and return hydrated PostgreSQL documents."""
    try:
        documents = await service.search(query)
    except SearchDependencyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search service is temporarily unavailable",
        ) from error
    return [DocumentResponse.model_validate(document) for document in documents]


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
    description="Deletes the Elasticsearch projection before the PostgreSQL source record.",
)
async def delete_document(
    document_id: int,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> Response:
    """Delete a document from Elasticsearch and PostgreSQL."""
    try:
        await service.delete(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from error
    except DeleteDependencyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document deletion is temporarily unavailable",
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)

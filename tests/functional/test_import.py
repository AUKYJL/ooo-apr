from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.scripts.import_data import ImportRecord, import_records
from app.search.index import DocumentIndex


@pytest.mark.asyncio
async def test_importer_persists_and_indexes_a_small_dataset(
    session: AsyncSession, document_index: DocumentIndex
) -> None:
    records = [
        ImportRecord("одинаковый текст", datetime(2024, 1, 1), ["one"]),
        ImportRecord("одинаковый текст", datetime(2024, 1, 2), ["two"]),
    ]

    assert await import_records(records, replace=True) == 2
    assert await session.scalar(select(func.count(Document.id))) == 2
    assert await document_index.search_ids("текст") == [2, 1]

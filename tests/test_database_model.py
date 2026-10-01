from sqlalchemy import BigInteger, DateTime, Text
from sqlalchemy.dialects.postgresql import ARRAY

from app.db.models import Document


def test_document_model_matches_required_schema() -> None:
    table = Document.__table__

    assert list(table.columns.keys()) == ["id", "rubrics", "text", "created_date"]
    assert isinstance(table.c.id.type, BigInteger)
    assert table.c.id.primary_key
    assert isinstance(table.c.rubrics.type, ARRAY)
    assert isinstance(table.c.rubrics.type.item_type, Text)
    assert isinstance(table.c.text.type, Text)
    assert isinstance(table.c.created_date.type, DateTime)
    assert table.c.created_date.type.timezone is False

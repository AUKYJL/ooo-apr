from datetime import datetime
from pathlib import Path

import pytest

from app.scripts.import_data import (
    ImportValidationError,
    parse_created_date,
    parse_rubrics,
    read_import_records,
)


def test_parse_rubrics_accepts_valid_list() -> None:
    assert parse_rubrics("['VK-1', 'VK-2']") == ["VK-1", "VK-2"]


def test_parse_rubrics_rejects_invalid_literal() -> None:
    with pytest.raises(ImportValidationError, match="invalid rubrics literal"):
        parse_rubrics("not a list", 7)


def test_parse_rubrics_rejects_non_list() -> None:
    with pytest.raises(ImportValidationError, match="rubrics must be a list"):
        parse_rubrics("'VK-1'", 7)


def test_parse_rubrics_rejects_non_string_item() -> None:
    with pytest.raises(ImportValidationError, match="every rubric must be a string"):
        parse_rubrics("['VK-1', 2]", 7)


def test_parse_created_date_requires_dataset_format() -> None:
    assert parse_created_date("2019-04-06 16:06:27") == datetime(2019, 4, 6, 16, 6, 27)
    with pytest.raises(ImportValidationError, match="created_date"):
        parse_created_date("2019/04/06", 4)


def test_duplicate_text_remains_two_records(tmp_path: Path) -> None:
    dataset = tmp_path / "posts.csv"
    dataset.write_text(
        "text,created_date,rubrics\n"
        'same,2019-04-06 16:06:27,"[\'VK-1\']"\n'
        'same,2019-04-07 16:06:27,"[\'VK-2\']"\n',
        encoding="utf-8",
    )

    records = read_import_records(dataset)

    assert len(records) == 2
    assert [record.text for record in records] == ["same", "same"]

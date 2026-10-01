"""Import the supplied CSV into PostgreSQL and its Elasticsearch projection."""

import argparse
import ast
import asyncio
import csv
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.models import Document
from app.db.session import dispose_engine, get_session_factory
from app.search.client import create_elasticsearch_client
from app.search.index import DocumentIndex, IndexDocument

LOGGER = logging.getLogger(__name__)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
REQUIRED_COLUMNS = frozenset({"text", "created_date", "rubrics"})


class ImportValidationError(ValueError):
    """A CSV value does not satisfy the documented dataset contract."""


@dataclass(frozen=True, slots=True)
class ImportRecord:
    """A fully validated CSV record, before it receives a database ID."""

    text: str
    created_date: datetime
    rubrics: list[str]


def parse_rubrics(value: str, row_number: int = 0) -> list[str]:
    """Safely parse and validate a source rubric list literal."""
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError) as error:
        raise ImportValidationError(f"row {row_number}: invalid rubrics literal") from error
    if not isinstance(parsed, list):
        raise ImportValidationError(f"row {row_number}: rubrics must be a list")
    if not all(isinstance(item, str) for item in parsed):
        raise ImportValidationError(f"row {row_number}: every rubric must be a string")
    return parsed


def parse_created_date(value: str, row_number: int = 0) -> datetime:
    """Parse the naive source timestamp with the dataset's exact format."""
    try:
        return datetime.strptime(value, DATE_FORMAT)
    except ValueError as error:
        raise ImportValidationError(
            f"row {row_number}: created_date must use {DATE_FORMAT}"
        ) from error


def read_import_records(path: Path) -> list[ImportRecord]:
    """Read the complete CSV and validate it before any store is changed."""
    try:
        with path.open(newline="", encoding="utf-8") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
                raise ImportValidationError(
                    "CSV must contain text, created_date, and rubrics columns"
                )
            records: list[ImportRecord] = []
            for row_number, row in enumerate(reader, start=2):
                if None in row.values():
                    raise ImportValidationError(f"row {row_number}: unexpected extra column")
                try:
                    text_value = row["text"]
                    date_value = row["created_date"]
                    rubrics_value = row["rubrics"]
                except KeyError as error:
                    message = f"row {row_number}: missing required value"
                    raise ImportValidationError(message) from error
                if text_value is None or date_value is None or rubrics_value is None:
                    raise ImportValidationError(f"row {row_number}: missing required value")
                records.append(
                    ImportRecord(
                        text=text_value,
                        created_date=parse_created_date(date_value, row_number),
                        rubrics=parse_rubrics(rubrics_value, row_number),
                    )
                )
    except OSError as error:
        raise ImportValidationError(f"cannot read CSV {path}: {error}") from error
    return records


async def import_records(records: Sequence[ImportRecord], *, replace: bool) -> int:
    """Persist validated records and rebuild their Elasticsearch projection when requested."""
    settings = get_settings()
    client = create_elasticsearch_client(settings)
    document_index = DocumentIndex(client, settings.elasticsearch_index)
    try:
        async with get_session_factory()() as session:
            existing_count = await session.scalar(select(func.count(Document.id)))
            if existing_count and not replace:
                raise RuntimeError("documents table is not empty; rerun with --replace")

            if replace:
                await document_index.recreate()
                await session.execute(text("TRUNCATE TABLE documents RESTART IDENTITY"))
            else:
                await document_index.ensure_exists()

            documents = [
                Document(
                    text=record.text,
                    created_date=record.created_date,
                    rubrics=record.rubrics,
                )
                for record in records
            ]
            session.add_all(documents)
            await session.flush()
            await session.commit()

        indexed_count = await document_index.bulk_index(
            IndexDocument(document.id, document.text, document.created_date)
            for document in documents
        )
        if indexed_count != len(documents):
            raise RuntimeError(
                f"Elasticsearch indexed {indexed_count} of {len(documents)} documents"
            )
        return len(documents)
    finally:
        await client.close()


def parse_arguments() -> argparse.Namespace:
    """Parse explicit importer command-line options."""
    parser = argparse.ArgumentParser(description="Import document CSV data")
    parser.add_argument("--path", required=True, type=Path, help="path to the input CSV")
    parser.add_argument("--replace", action="store_true", help="reset existing documents and index")
    return parser.parse_args()


async def run(path: Path, *, replace: bool) -> int:
    """Validate then import a CSV, returning the imported record count."""
    records = read_import_records(path)
    try:
        count = await import_records(records, replace=replace)
    finally:
        await dispose_engine()
    LOGGER.info("Imported %d documents from %s", count, path)
    return count


def main() -> None:
    """Run the importer command."""
    arguments = parse_arguments()
    configure_logging()
    try:
        asyncio.run(run(arguments.path, replace=arguments.replace))
    except (ImportValidationError, RuntimeError) as error:
        raise SystemExit(f"Import failed: {error}") from error


if __name__ == "__main__":
    main()

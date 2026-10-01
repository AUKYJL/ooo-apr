"""Write the deterministic checked-in OpenAPI schema."""

import argparse
import json
from pathlib import Path

from app.main import create_app

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "docs.json"


def render_openapi() -> str:
    """Render the application OpenAPI schema deterministically."""
    return json.dumps(create_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    """Export the OpenAPI schema to the repository root."""
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI schema")
    parser.add_argument("--check", action="store_true", help="fail when docs.json is stale")
    arguments = parser.parse_args()
    rendered_schema = render_openapi()
    if arguments.check:
        try:
            current_schema = OUTPUT_PATH.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise SystemExit("docs.json is missing; run make docs") from error
        if current_schema != rendered_schema:
            raise SystemExit("docs.json is stale; run make docs")
        return
    OUTPUT_PATH.write_text(rendered_schema, encoding="utf-8")


if __name__ == "__main__":
    main()

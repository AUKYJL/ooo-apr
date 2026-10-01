"""Small, dependency-free application logging configuration."""

import logging


def configure_logging() -> None:
    """Configure readable process logs when no host configuration exists."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

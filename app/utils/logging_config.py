"""
Centralized logging configuration.

Call setup_logging() once at startup (in app/main.py or standalone scripts)
before any other imports that use logging.
"""

import logging
import os


def setup_logging():
    """Configure root logger from LOG_LEVEL env var (default: INFO)."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Pin noisy third-party loggers to WARNING unless we're at DEBUG
    if level > logging.DEBUG:
        for name in ("httpx", "uvicorn", "uvicorn.access", "httpcore"):
            logging.getLogger(name).setLevel(logging.WARNING)

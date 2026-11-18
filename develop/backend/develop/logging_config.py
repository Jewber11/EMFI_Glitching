"""Centralized logging configuration for the Develop service.

Call ``setup_logging()`` once at import time (in main.py) to configure the
root logger for both console and file output.  Every other module simply does:

    import logging
    log = logging.getLogger(__name__)

The log file is written to ``$EMFI_LOG_DIR/develop.log`` (default
``<repo>/develop/logs/develop.log``).  The file handler uses a
``RotatingFileHandler`` so a single run can't eat the disk.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
)
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

DEFAULT_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
BACKUP_COUNT = 5


def setup_logging(level: str | None = None) -> Path:
    """Configure root logger with console + rotating file handlers.

    Returns the path to the active log file.
    """
    effective_level = getattr(
        logging, (level or os.environ.get("EMFI_LOG_LEVEL", "INFO")).upper()
    )

    log_dir = Path(os.environ.get("EMFI_LOG_DIR", str(DEFAULT_LOG_DIR)))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "develop.log"

    root = logging.getLogger()
    root.setLevel(effective_level)

    # Avoid duplicate handlers on repeated calls (e.g. test reloads).
    if root.handlers:
        return log_file

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(effective_level)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT
    )
    file_handler.setLevel(effective_level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Quieten noisy third-party loggers.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    return log_file

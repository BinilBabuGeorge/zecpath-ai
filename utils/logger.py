"""
Centralized logging setup for the Zecpath AI system.

Every module (ats_engine, screening_ai, interview_ai, scoring, etc.)
should import get_logger() instead of configuring logging itself.
This keeps log format, level, and output location consistent
across the whole codebase.

Usage:
    from utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("ATS scoring started for candidate %s", candidate_id)
"""

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
LOG_FILE = os.path.join(LOG_DIR, "zecpath_ai.log")
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure_root_logger(level: int = logging.INFO) -> None:
    """Configure the root logger once: console + rotating file handler."""
    global _configured
    if _configured:
        return

    os.makedirs(LOG_DIR, exist_ok=True)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    _configured = True


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a module-level logger with console + file output configured."""
    _configure_root_logger(level)
    return logging.getLogger(name)

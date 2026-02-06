from __future__ import annotations

import logging
import os

DEFAULT_LEVEL = "INFO"
DEFAULT_FORMAT = "%(asctime)s | %(levelname)s | %(message)s"
DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _resolve_level(level: str | int | None) -> int:
    if level is None:
        level = os.getenv("JOBSCOPE_LOG_LEVEL", DEFAULT_LEVEL)

    if isinstance(level, int):
        return level

    if not isinstance(level, str):
        return logging.INFO

    level_str = level.strip().upper()
    if level_str.isdigit():
        try:
            return int(level_str)
        except ValueError:
            return logging.INFO

    return getattr(logging, level_str, logging.INFO)


def configure_logging(level: str | int | None = None) -> None:
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    if root.handlers:
        _configured = True
        return

    resolved_level = _resolve_level(level)
    logging.basicConfig(
        level=resolved_level, format=DEFAULT_FORMAT, datefmt=DEFAULT_DATEFMT
    )
    _configured = True


def get_logger(name: str | None = None) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name or "jobscope")


__all__ = ["configure_logging", "get_logger"]

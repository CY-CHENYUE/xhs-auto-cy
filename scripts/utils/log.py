"""Structured logging setup for xhs-auto-cy."""

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Output log records as single-line JSON for easy parsing."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "module": record.module,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


class PrettyFormatter(logging.Formatter):
    """Human-readable colored output for terminal use."""

    COLORS = {
        "DEBUG": "\033[90m",
        "INFO": "\033[36m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[1;31m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.now().strftime("%H:%M:%S")
        prefix = f"{color}[{ts}][{record.module}]{self.RESET}"
        msg = record.getMessage()
        if record.exc_info and record.exc_info[0] is not None:
            msg += "\n" + self.formatException(record.exc_info)
        return f"{prefix} {msg}"


def setup_logging(level: str = "INFO", fmt: str = "pretty") -> logging.Logger:
    """Initialize and return the root logger for xhs-auto-cy.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR).
        fmt: Output format - "json" for structured, "pretty" for terminal.
    """
    logger = logging.getLogger("xhs")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stderr)
    if fmt == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(PrettyFormatter())
    logger.addHandler(handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the xhs namespace."""
    return logging.getLogger(f"xhs.{name}")

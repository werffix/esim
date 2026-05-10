import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from app.core.config import settings


def add_severity(logger: Any, method: str, event_dict: EventDict) -> EventDict:
    """Map structlog level to GCP severity."""
    level = event_dict.get("level", method).upper()
    mapping = {
        "DEBUG": "DEBUG",
        "INFO": "INFO",
        "WARNING": "WARNING",
        "ERROR": "ERROR",
        "CRITICAL": "CRITICAL",
    }
    event_dict["severity"] = mapping.get(level, "DEFAULT")
    return event_dict


def setup_logging() -> None:
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.LOG_FORMAT == "json":
        processors = shared_processors + [
            add_severity,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Quiet noisy libraries
    for lib in ("httpx", "httpcore", "aiogram", "sqlalchemy.engine"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    return structlog.get_logger(name)

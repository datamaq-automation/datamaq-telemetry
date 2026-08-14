import logging
import sys
from typing import Any

import structlog

from src.infrastructure.settings.config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.LOG_FORMAT.lower() == "json":
        # Formato JSON compacto para producción en VPS (Grafana Loki, Promtail, etc.)
        renderer_processor = structlog.processors.JSONRenderer()
        timestamp_processor = structlog.processors.TimeStamper(fmt="iso", utc=True)
    else:
        # Formato consola limpio y coloreado para desarrollo local (sin ruido)
        renderer_processor = structlog.dev.ConsoleRenderer(
            colors=sys.stdout.isatty(),
            pad_event=28,
        )
        timestamp_processor = structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False)

    structlog.configure(
        processors=[
            *shared_processors,
            timestamp_processor,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[*shared_processors, timestamp_processor],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer_processor,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(log_level)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Silenciar logs excesivamente verbosos de librerías externas
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING if not settings.DEBUG else logging.INFO)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)

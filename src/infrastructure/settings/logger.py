import logging
import os
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

from src.domain.telemetria.ports import LoggerPort
from src.infrastructure.settings.config import get_settings

# Colores ANSI estilo Uvicorn
COLOR_RESET = "\033[0m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_RED = "\033[31m"
COLOR_BLUE = "\033[36m"
COLOR_PURPLE = "\033[35m"
COLOR_DIM = "\033[2m"

LEVEL_STYLES: dict[str, tuple[str, str]] = {
    "debug": ("DEBUG:   ", COLOR_BLUE),
    "info": ("INFO:    ", COLOR_GREEN),
    "warning": ("WARNING: ", COLOR_YELLOW),
    "error": ("ERROR:   ", COLOR_RED),
    "critical": ("CRITICAL:", COLOR_PURPLE),
}


def uvicorn_style_renderer(_: WrappedLogger, __: str, event_dict: EventDict) -> str:
    """Renderizador para consola que replica exactamente la estética de Uvicorn."""
    level = str(event_dict.pop("level", "info")).lower()
    logger_name = event_dict.pop("logger", "") or event_dict.pop("logger_name", "")
    event = event_dict.pop("event", "")
    exc_info = event_dict.pop("exc_info", None)
    stack_info = event_dict.pop("stack_info", None)

    prefix_text, color = LEVEL_STYLES.get(level, (f"{level.upper()}:", COLOR_GREEN))

    is_tty = sys.stdout.isatty()
    level_prefix = f"{color}{prefix_text}{COLOR_RESET}" if is_tty else prefix_text
    logger_tag = f"({logger_name.upper()}) " if logger_name else ""

    # Formatear parámetros adicionales como key=val
    kv_parts = []
    for k, v in event_dict.items():
        if k.startswith("_"):
            continue
        val_str = str(v)
        kv_parts.append(f"{COLOR_DIM}{k}={COLOR_RESET}{val_str}" if is_tty else f"{k}={val_str}")

    kv_string = (" " + " ".join(kv_parts)) if kv_parts else ""
    line = f"{level_prefix} {logger_tag}{event}{kv_string}"

    if exc_info:
        line += f"\n{exc_info}"
    if stack_info:
        line += f"\n{stack_info}"

    return line


def setup_logging() -> None:
    settings = get_settings()
    log_level_name = os.environ.get("LOG_LEVEL", settings.LOG_LEVEL).upper()
    if "--debug" in sys.argv or "-d" in sys.argv:
        log_level_name = "DEBUG"
    log_level = getattr(logging, log_level_name, logging.INFO)

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
        # Formato consola idéntico a Uvicorn para desarrollo local limpio
        renderer_processor = uvicorn_style_renderer
        timestamp_processor = None

    proc_list = [p for p in shared_processors if p is not None]
    if timestamp_processor:
        proc_list.append(timestamp_processor)

    structlog.configure(
        processors=[
            *proc_list,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=proc_list,
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


class StructlogAdapter(LoggerPort):
    """Adaptador de infraestructura que implementa LoggerPort sobre structlog."""

    def __init__(self, logger: structlog.stdlib.BoundLogger):
        self._logger = logger

    def info(self, evento: str, **kwargs: object) -> None:
        self._logger.info(evento, **kwargs)

    def warning(self, evento: str, **kwargs: object) -> None:
        self._logger.warning(evento, **kwargs)

    def error(self, evento: str, **kwargs: object) -> None:
        self._logger.error(evento, **kwargs)

    def debug(self, evento: str, **kwargs: object) -> None:
        self._logger.debug(evento, **kwargs)


def get_logger(name: str) -> LoggerPort:
    return StructlogAdapter(structlog.get_logger(name))

"""tests/unit/test_logger_setup.py — Pruebas de la configuración de logging (logger.py)."""

import logging
import sys
from unittest.mock import MagicMock

from src.infrastructure.settings.config import get_settings
from src.infrastructure.settings.logger import (
    StructlogAdapter,
    get_logger,
    redactar_secretos,
    setup_logging,
    uvicorn_style_renderer,
)


def test_redactar_secretos():
    event_dict = {
        "username": "operador",
        "password": "secreto",
        "authorization": "Bearer abc",
        "api_key": "k",
        "clave": "c",
        "nivel": "info",
    }

    resultado = redactar_secretos(None, "", event_dict)

    assert resultado["password"] == "***"
    assert resultado["authorization"] == "***"
    assert resultado["api_key"] == "***"
    assert resultado["clave"] == "***"
    assert resultado["username"] == "operador"
    assert resultado["nivel"] == "info"


def test_uvicorn_style_renderer_basico():
    event_dict = {
        "level": "info",
        "logger": "server",
        "event": "servidor_listo",
        "puerto": 8000,
        "_interno": "omitido",
    }

    linea = uvicorn_style_renderer(None, "", event_dict)

    assert "INFO:" in linea
    assert "(SERVER)" in linea
    assert "servidor_listo" in linea
    assert "puerto=8000" in linea
    assert "_interno" not in linea


def test_uvicorn_style_renderer_con_exc_y_stack():
    event_dict = {
        "level": "error",
        "event": "fallo",
        "exc_info": "Traceback...",
        "stack_info": "stack...",
    }

    linea = uvicorn_style_renderer(None, "", event_dict)

    assert "ERROR:" in linea
    assert "Traceback..." in linea
    assert "stack..." in linea


def test_uvicorn_style_renderer_nivel_desconocido():
    linea = uvicorn_style_renderer(None, "", {"level": "trace", "event": "e"})

    assert "TRACE:" in linea


def test_setup_logging_console(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "console")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    get_settings.cache_clear()

    setup_logging()

    assert logging.getLogger().handlers


def test_setup_logging_json(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    get_settings.cache_clear()

    setup_logging()

    assert logging.getLogger().handlers


def test_setup_logging_debug_flag(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setattr(sys, "argv", ["pytest", "--debug"])
    get_settings.cache_clear()

    setup_logging()


def test_structlog_adapter():
    mock = MagicMock()
    adapter = StructlogAdapter(mock)

    adapter.info("ev", clave="v")
    adapter.warning("ev2")
    adapter.error("ev3")
    adapter.debug("ev4")

    mock.info.assert_called_once_with("ev", clave="v")
    mock.warning.assert_called_once_with("ev2")
    mock.error.assert_called_once_with("ev3")
    mock.debug.assert_called_once_with("ev4")


def test_get_logger_devuelve_adapter():
    logger = get_logger("test")

    assert isinstance(logger, StructlogAdapter)

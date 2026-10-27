"""tests/unit/test_ip_cliente.py — Pruebas de extracción de IP y protección anti-spoofing (#66)."""

import asyncio
from unittest.mock import MagicMock

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.types import Scope
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from src.infrastructure.fastapi.error_handler import manejar_404
from src.infrastructure.fastapi.ip_cliente import extraer_ip_cliente
from src.infrastructure.fastapi.routes.auth_router import _obtener_ip_cliente
from src.infrastructure.fastapi.seguridad_rutas import _extraer_ip_cliente


def test_proxy_headers_middleware_resuelve_ip_real_con_cliente_127_0_0_1():
    """1. Test base: ProxyHeadersMiddleware con 127.0.0.1 y 'X-Forwarded-For: 1.2.3.4, 203.0.113.9'

    resuelve client.host como 203.0.113.9 (último salto confiable antes de Nginx).
    """
    captura: dict[str, tuple[str, int] | None] = {}

    async def dummy_app(scope: Scope, receive, send):
        captura["client"] = scope.get("client")

    app = ProxyHeadersMiddleware(dummy_app, trusted_hosts="127.0.0.1")

    scope: Scope = {
        "type": "http",
        "client": ("127.0.0.1", 54321),
        "headers": [
            (b"x-forwarded-for", b"1.2.3.4, 203.0.113.9"),
        ],
    }

    async def run():
        await app(scope, None, None)

    asyncio.run(run())

    assert captura["client"] is not None
    assert captura["client"][0] == "203.0.113.9"


def test_extraer_ip_cliente_desde_request_ignora_x_forwarded_for():
    """El backend no lee X-Forwarded-For directamente del Request; confía en request.client.host."""
    request = MagicMock(spec=Request)
    request.headers = {"X-Forwarded-For": "10.0.0.1, 1.2.3.4"}
    request.client.host = "203.0.113.9"

    ip = extraer_ip_cliente(request)
    assert ip == "203.0.113.9"
    assert _obtener_ip_cliente(request) == "203.0.113.9"


def test_extraer_ip_cliente_desde_scope_asgi_ignora_x_forwarded_for():
    """El middleware ASGI extrae la IP de scope['client'] e ignora cabeceras x-forwarded-for."""
    scope: Scope = {
        "type": "http",
        "client": ("203.0.113.9", 1234),
        "headers": [(b"x-forwarded-for", b"10.0.0.1, 1.2.3.4")],
    }

    ip = extraer_ip_cliente(scope)
    assert ip == "203.0.113.9"
    assert _extraer_ip_cliente(scope) == "203.0.113.9"


def test_extraer_ip_cliente_fallbacks():
    """Casos de fallback cuando el cliente es nulo o desconocido."""
    assert extraer_ip_cliente(None) == "desconocida"
    assert extraer_ip_cliente(None, fallback="desconocido") == "desconocido"

    req_sin_client = MagicMock(spec=Request)
    req_sin_client.client = None
    assert extraer_ip_cliente(req_sin_client) == "desconocida"

    scope_sin_client: Scope = {"type": "http", "client": None}
    assert extraer_ip_cliente(scope_sin_client, fallback="desconocido") == "desconocido"


def test_error_handler_404_registra_ip_real_sin_spoofing(monkeypatch):
    """El log de 404 usa la IP real de request.client.host y no el valor manipulado en x-forwarded-for."""
    mock_logger = MagicMock()
    monkeypatch.setattr("structlog.get_logger", lambda name: mock_logger)

    request = MagicMock(spec=Request)
    request.url.path = "/ruta-inexistente"
    request.method = "GET"
    request.client.host = "203.0.113.9"
    request.headers = {"x-forwarded-for": "1.2.3.4"}

    exc = StarletteHTTPException(status_code=404, detail="Not Found")
    manejar_404(request, exc)

    assert mock_logger.warning.called
    kwargs = mock_logger.warning.call_args[1]
    assert kwargs.get("ip") == "203.0.113.9"

"""src/infrastructure/fastapi/middleware.py — Middleware de correlación de requests: genera y propaga un request_id único."""

import uuid
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from src.infrastructure.fastapi.solo_lectura_middleware import SoloLecturaMiddleware, excepciones_desde_config


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Vincula un request_id único a cada request y lo emite en el header X-Request-ID."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()


def registrar_guard_solo_lectura(app: Any, settings: Any) -> None:
    """Agrega el guard de solo lectura solo si API_SOLO_LECTURA está activo (decisión 2026-10-29, D1)."""
    if settings.API_SOLO_LECTURA:
        app.add_middleware(
            SoloLecturaMiddleware, excepciones=excepciones_desde_config(settings.API_SOLO_LECTURA_EXCEPCIONES)
        )

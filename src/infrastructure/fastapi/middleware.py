"""src/infrastructure/fastapi/middleware.py — Middleware de correlación de requests: genera y propaga un request_id único."""

import uuid
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from src.infrastructure.fastapi.solo_lectura_middleware import (
    BloqueoEscrituraSoloLecturaMiddleware,
    SoloLecturaMiddleware,
    excepciones_desde_config,
    excepciones_efectivas,
)


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
    """Bloquea escrituras del rol solo_lectura en toda instancia, y el guard de método en api-dev (D1)."""
    app.add_middleware(
        BloqueoEscrituraSoloLecturaMiddleware,
        secreto=settings.API_SECRET_KEY,
        secreto_anterior=settings.API_SECRET_KEY_ANTERIOR,
        nombre_cookie=settings.AUTH_COOKIE_NOMBRE,
    )
    if settings.API_SOLO_LECTURA:
        excepciones = excepciones_efectivas(
            excepciones_desde_config(settings.API_SOLO_LECTURA_EXCEPCIONES), settings.DB_NAME
        )
        app.add_middleware(SoloLecturaMiddleware, excepciones=excepciones)

"""Middleware de headers de seguridad para endurecer toda respuesta HTTP."""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from src.infrastructure.settings.config import Settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Añade headers de seguridad a todas las respuestas de la API."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"

        if not self._settings.DEBUG:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        if self._settings.CSP_HEADER:
            response.headers["Content-Security-Policy"] = self._settings.CSP_HEADER

        return response

"""src/infrastructure/fastapi/duracion_requests.py — Duración de punta a punta de cada request HTTP (#14).

Hasta ahora no había ninguna medición de punta a punta: la latencia del unifilar se reconstruyó desde logs sueltos
porque nginx no registra `$request_time`. Este middleware deja una línea INFO por request con la ruta como
plantilla (`/plantas/{planta_id}/...`, sin IDs), el estado HTTP, `duracion_ms` y el `request_id`.

Es ASGI puro (no `BaseHTTPMiddleware`) para no bufferizar respuestas en streaming y para medir hasta el último byte.
Va por dentro de `RequestIdMiddleware`, que ya dejó el `request_id` en `scope["state"]`.
"""

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.infrastructure.settings.logger import get_logger

logger = get_logger("http")

RUTA_SIN_PLANTILLA = "sin_ruta"
"""Requests que no matchearon ninguna ruta (404) o que atendió una app montada sin plantilla."""


class DuracionRequestMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inicio = time.perf_counter()
        estado_http = 500  # Si la app lanza antes de responder, el servidor contesta 500.

        async def _send(message: Message) -> None:
            nonlocal estado_http
            if message["type"] == "http.response.start":
                estado_http = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            ruta = scope.get("route")
            logger.info(
                "http_request_completado",
                metodo=scope.get("method"),
                ruta=getattr(ruta, "path", None) or RUTA_SIN_PLANTILLA,
                estado_http=estado_http,
                duracion_ms=round((time.perf_counter() - inicio) * 1000, 1),
                request_id=scope.get("state", {}).get("request_id"),
            )

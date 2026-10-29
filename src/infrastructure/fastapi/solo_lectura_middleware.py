"""src/infrastructure/fastapi/solo_lectura_middleware.py — Guard de método para la API de solo lectura (develop/api-dev).

Decisión 2026-10-29 (spec `specs/develop-replica-y-flujo-en-vivo.md` 3.4, D1): aplica a **todas** las sesiones de
api-dev, no solo a una cuenta. Va como middleware ASGI, por fuera de los guards de rol, así que no depende de cómo
esté armado cada router. Solo se registra cuando `API_SOLO_LECTURA=true`.
"""

import json
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

METODOS_LECTURA = frozenset({"GET", "HEAD", "OPTIONS"})


def excepciones_desde_config(texto: str) -> frozenset[str]:
    """Rutas exactas que siguen aceptando métodos que escriben. Vacío por defecto."""
    return frozenset(r.strip() for r in texto.split(",") if r.strip())


class SoloLecturaMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]], excepciones: Iterable[str] = ()) -> None:
        self.app = app
        self.excepciones = frozenset(excepciones)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope["method"] in METODOS_LECTURA or scope["path"] in self.excepciones:
            await self.app(scope, receive, send)
            return
        cuerpo = json.dumps({"detail": "api de solo lectura: esta instancia no acepta escrituras"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(cuerpo)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": cuerpo})

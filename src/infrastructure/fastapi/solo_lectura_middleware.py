"""src/infrastructure/fastapi/solo_lectura_middleware.py — Guard de método para la API de solo lectura (develop/api-dev).

Decisión 2026-10-29 (spec `specs/develop-replica-y-flujo-en-vivo.md` 3.4, D1): aplica a **todas** las sesiones de
api-dev, no solo a una cuenta. Va como middleware ASGI, por fuera de los guards de rol, así que no depende de cómo
esté armado cada router. Solo se registra cuando `API_SOLO_LECTURA=true`.
"""

import json
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from starlette.requests import Request

from src.infrastructure.auth.jwt_token_service import JwtTokenService

METODOS_LECTURA = frozenset({"GET", "HEAD", "OPTIONS"})


BASE_COPIA_DEV = "datamaq_telemetry_dev_snapshot"
"""Copia de desarrollo restaurada, única base donde se permite una excepción de escritura (P1, opción B)."""

RUTAS_EXCEPCION_PERMITIDAS = frozenset({"/api/v1/auth/login"})
"""Rutas que pueden tener una excepción. Solo login: sus escrituras son auditoría y, con dispositivo de confianza,
`dispositivos_confiables`. Ninguna otra ruta puede quedar exenta, aunque la configuración la pida."""


def excepciones_desde_config(texto: str) -> frozenset[str]:
    """Rutas exactas que la configuración pide dejar escribir. Vacío por defecto."""
    return frozenset(r.strip() for r in texto.split(",") if r.strip())


def excepciones_efectivas(configuradas: frozenset[str], nombre_base: str) -> frozenset[str]:
    """Excepciones que realmente aplican: solo en la base de la copia y solo para rutas permitidas.

    Si la conexión apuntara a producción u otra base, devuelve vacío y el guard niega igual.
    """
    if nombre_base != BASE_COPIA_DEV:
        return frozenset()
    return configuradas & RUTAS_EXCEPCION_PERMITIDAS


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


ROL_SOLO_LECTURA = "solo_lectura"
RUTAS_LOGOUT_Y_LOGIN = frozenset({"/api/v1/auth/login", "/api/v1/auth/logout"})
"""Únicas rutas no GET que puede usar el rol de solo lectura: entrar y salir de su propia sesión."""


class BloqueoEscrituraSoloLecturaMiddleware:
    """Rechaza con 403 cualquier método que escribe cuando el token es de rol `solo_lectura`.

    Va en todas las instancias (el rol existe en cualquier ambiente). Verifica la firma del token igual que
    `get_usuario_actual`, pero no depende de un guard de ruta: así cubre también rutas que no resuelven usuario,
    como `POST /api/v1/dispositivos/{id}/realtime` (issue #99). Si el token no verifica, no bloquea: esas rutas
    siguen con su propia autenticación.
    """

    def __init__(self, app: Any, secreto: str, secreto_anterior: str, nombre_cookie: str) -> None:
        self.app = app
        self.verificador = JwtTokenService(secreto)
        self.secretos_adicionales = [secreto_anterior] if secreto_anterior else None
        self.nombre_cookie = nombre_cookie

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] in METODOS_LECTURA
            or scope["path"] in RUTAS_LOGOUT_Y_LOGIN
            or not self._es_solo_lectura(scope)
        ):
            await self.app(scope, receive, send)
            return
        cuerpo = json.dumps({"detail": "rol solo_lectura: no puede escribir"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(cuerpo)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": cuerpo})

    def _es_solo_lectura(self, scope: dict[str, Any]) -> bool:
        # Misma regla de extracción que `extraer_token`: cookie primero, después Bearer.
        request = Request(scope)
        cookie = request.cookies.get(self.nombre_cookie)
        authorization = request.headers.get("authorization")
        token = cookie or (
            authorization.removeprefix("Bearer ").strip()
            if authorization and authorization.startswith("Bearer ")
            else None
        )
        if not token:
            return False
        claims = self.verificador.verificar(token, self.secretos_adicionales)
        return claims is not None and claims.get("rol") == ROL_SOLO_LECTURA

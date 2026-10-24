"""src/infrastructure/fastapi/seguridad_rutas.py — Middlewares de seguridad: rechazo de path traversal y rate limiting 404."""

import time
import urllib.parse
from collections import OrderedDict

import structlog
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.infrastructure.settings.config import Settings

logger = structlog.get_logger("security")

MAX_IPS_RATE_LIMIT = 5000


def contiene_secuencia_insegura(path: str, raw_path: bytes | None = None) -> tuple[bool, str]:
    """Evalúa si una ruta contiene secuencias de path traversal, caracteres nulos o secuencias de escape."""
    # 1. Caracteres nulos / de control
    if "\x00" in path or (raw_path and b"\x00" in raw_path):
        return True, "caracter_nulo"

    for ch in path:
        code = ord(ch)
        if code < 32 or code == 127:
            return True, "caracter_control"

    # 2. Path traversal en el path o en el raw_path
    if ".." in path:
        return True, "path_traversal"

    if raw_path:
        raw_lower = raw_path.lower()
        if b"%2e%2e" in raw_lower or b"%252e" in raw_lower:
            return True, "path_traversal_encoded"

    # 3. Decodificación adicional por múltiples codificaciones URL
    try:
        unquoted = urllib.parse.unquote(path)
        if ".." in unquoted:
            return True, "path_traversal_doble_encoding"
    except Exception:
        return True, "path_invalido"

    return False, ""


def _extraer_ip_cliente(scope: Scope) -> str:
    """Extrae la IP del cliente considerando X-Forwarded-For si está disponible."""
    headers = dict(scope.get("headers", []))
    xff = headers.get(b"x-forwarded-for")
    if xff:
        return xff.decode("latin-1", "replace").split(",")[0].strip()
    client = scope.get("client")
    if client and client[0]:
        return str(client[0])
    return "desconocido"


class RechazoPathInseguroMiddleware:
    """Interrumpe tempranamente peticiones con path traversal o caracteres de control antes del ruteo."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            raw_path = scope.get("raw_path")
            inseguro, motivo = contiene_secuencia_insegura(path, raw_path)
            if inseguro:
                client_ip = _extraer_ip_cliente(scope)
                logger.warning(
                    "rechazo_path_inseguro",
                    path=path,
                    motivo=motivo,
                    ip=client_ip,
                )
                if scope["type"] == "http":
                    response = JSONResponse(
                        status_code=400,
                        content={"detail": "Bad Request"},
                    )
                    await response(scope, receive, send)
                    return
                elif scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 4400})
                    return

        await self.app(scope, receive, send)


class RateLimit404Middleware:
    """Aplica límite de tasa a IPs no autenticadas que acumulen un pico de respuestas 404 consecutivas."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self._max_intentos = settings.RATE_LIMIT_404_MAX_INTENTOS
        self._ventana_seg = settings.RATE_LIMIT_404_VENTANA_SEGUNDOS
        self._historial_404: OrderedDict[str, list[float]] = OrderedDict()

    def _es_peticion_autenticada(self, scope: Scope) -> bool:
        headers = dict(scope.get("headers", []))
        if b"authorization" in headers:
            return True
        cookie_header = headers.get(b"cookie", b"").decode("latin-1", "replace")
        return "datamaq_token=" in cookie_header

    def _esta_bloqueada(self, ip: str, ahora: float) -> tuple[bool, int]:
        if self._max_intentos <= 0 or ip == "desconocido":
            return False, 0
        historial = self._historial_404.get(ip)
        if not historial:
            return False, 0
        umbral = ahora - self._ventana_seg
        historial_activo = [t for t in historial if t > umbral]
        self._historial_404[ip] = historial_activo
        if len(historial_activo) >= self._max_intentos:
            segundos_restantes = int(max(1.0, (historial_activo[0] + self._ventana_seg) - ahora))
            return True, segundos_restantes
        return False, 0

    def _registrar_404(self, ip: str, ahora: float) -> None:
        if self._max_intentos <= 0 or ip == "desconocido":
            return
        if ip in self._historial_404:
            self._historial_404.move_to_end(ip)
        elif len(self._historial_404) >= MAX_IPS_RATE_LIMIT:
            self._historial_404.popitem(last=False)

        historial = self._historial_404.setdefault(ip, [])
        umbral = ahora - self._ventana_seg
        historial = [t for t in historial if t > umbral]
        historial.append(ahora)
        self._historial_404[ip] = historial

    def _limpiar_exito(self, ip: str) -> None:
        if ip in self._historial_404:
            del self._historial_404[ip]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._max_intentos <= 0:
            await self.app(scope, receive, send)
            return

        autenticado = self._es_peticion_autenticada(scope)
        client_ip = _extraer_ip_cliente(scope)
        ahora = time.monotonic()

        if not autenticado:
            bloqueada, retry_after = self._esta_bloqueada(client_ip, ahora)
            if bloqueada:
                logger.warning(
                    "rate_limit_404_bloqueado",
                    ip=client_ip,
                    retry_after=retry_after,
                    path=scope.get("path", ""),
                )
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Demasiadas solicitudes no encontradas"},
                    headers={"Retry-After": str(retry_after)},
                )
                await response(scope, receive, send)
                return

        status_code = 200

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
            await send(message)

        await self.app(scope, receive, send_wrapper)

        if not autenticado:
            if status_code == 404:
                self._registrar_404(client_ip, time.monotonic())
            elif status_code < 400:
                self._limpiar_exito(client_ip)

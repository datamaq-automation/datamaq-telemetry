"""src/infrastructure/fastapi/ip_cliente.py — Extracción confiable de IP del cliente (#66)."""

from typing import Any

from starlette.requests import Request
from starlette.types import Scope

FALLBACK_IP_DESCONOCIDA = "desconocida"


def extraer_ip_cliente(fuente: Request | Scope | Any | None, fallback: str = FALLBACK_IP_DESCONOCIDA) -> str:
    """Extrae la IP del cliente a partir de request.client.host o scope['client'].

    En producción y staging, Nginx reenvía la conexión al backend en 127.0.0.1.
    Uvicorn (con ProxyHeadersMiddleware y forwarded_allow_ips=127.0.0.1) puebla
    de forma confiable el campo `client` con la IP real del cliente (el último salto
    agregado por Nginx).

    Para evitar spoofing de IP, ningún módulo backend lee directamente X-Forwarded-For.
    """
    if fuente is None:
        return fallback

    # 1. Objeto Request o WebSocket de Starlette/FastAPI
    client = getattr(fuente, "client", None)
    if client is not None:
        host = getattr(client, "host", None)
        if host:
            return str(host)

    # 2. Diccionario ASGI Scope
    if isinstance(fuente, dict):
        scope_client = fuente.get("client")
        if scope_client and scope_client[0]:
            return str(scope_client[0])

    return fallback

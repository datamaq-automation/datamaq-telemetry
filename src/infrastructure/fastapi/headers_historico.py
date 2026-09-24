"""src/infrastructure/fastapi/headers_historico.py — Headers de metadatos de los históricos de potencia."""

import threading
import time
from collections.abc import Callable, Hashable
from datetime import datetime, timezone

import structlog
from fastapi import Response

# Fecha más antigua consultable del histórico (ISO 8601 UTC). Va en header y no en el body para
# que el contrato siga siendo la lista de siempre (cambio aditivo, sin despliegue coordinado).
HEADER_DATOS_DESDE = "X-Datos-Desde"

# P99 de la potencia activa en los últimos 30 días, en W (decimal). No depende de `hours` ni de
# `hasta`: es lo que mantiene fija la escala del eje Y al navegar ◀ ▶. Se omite sin datos suficientes.
HEADER_POTENCIA_REFERENCIA = "X-Potencia-Referencia-W"

# El P99 de 30 días casi no cambia en minutos y se pide en cada carga y en cada ◀ ▶.
TTL_POTENCIA_REFERENCIA_SEGUNDOS = 15 * 60


def formatear_datos_desde(valor: datetime) -> str:
    utc = valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor.astimezone(timezone.utc)
    return utc.isoformat().replace("+00:00", "Z")


def formatear_potencia_referencia(valor: float) -> str:
    return f"{valor:.1f}"


class CacheTTL:
    """Caché en memoria por proceso con expiración. Guarda también ``None`` (sin datos
    suficientes) para no recalcular 30 días en cada pedido de un medidor recién instalado.
    El cálculo corre fuera del lock: dos pedidos simultáneos pueden calcular dos veces."""

    def __init__(self, ttl_segundos: float, reloj: Callable[[], float] = time.monotonic):
        self._ttl = ttl_segundos
        self._reloj = reloj
        self._valores: dict[Hashable, tuple[float, float | None]] = {}
        self._lock = threading.Lock()

    def obtener(self, clave: Hashable, calcular: Callable[[], float | None]) -> float | None:
        ahora = self._reloj()
        with self._lock:
            entrada = self._valores.get(clave)
            if entrada is not None and entrada[0] > ahora:
                return entrada[1]
        valor = calcular()
        with self._lock:
            self._valores = {c: e for c, e in self._valores.items() if e[0] > ahora}
            self._valores[clave] = (ahora + self._ttl, valor)
        return valor

    def limpiar(self) -> None:
        with self._lock:
            self._valores.clear()


_log = structlog.get_logger(__name__)

cache_potencia_referencia = CacheTTL(TTL_POTENCIA_REFERENCIA_SEGUNDOS)


def setear_potencia_referencia(response: Response, clave: Hashable, calcular: Callable[[], float | None]) -> None:
    """Pone el header con el valor cacheado; lo omite sin datos suficientes. Es un metadato
    opcional: si el cálculo falla se loguea y se omite, sin tirar abajo el histórico."""
    try:
        valor = cache_potencia_referencia.obtener(clave, calcular)
    except Exception as e:
        _log.warning("potencia_referencia_fallida", clave=str(clave), tipo=type(e).__name__, error=str(e))
        return
    if valor is not None:
        response.headers[HEADER_POTENCIA_REFERENCIA] = formatear_potencia_referencia(valor)

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

    Un solo cálculo por clave a la vez: el dashboard pide gráfico e histograma en paralelo al
    mismo endpoint, y sin esto los dos calculaban (visto en producción, ~1,2 s cada uno). El
    segundo pedido espera al primero y usa su resultado; claves distintas no se bloquean."""

    def __init__(self, ttl_segundos: float, reloj: Callable[[], float] = time.monotonic):
        self._ttl = ttl_segundos
        self._reloj = reloj
        self._valores: dict[Hashable, tuple[float, float | None]] = {}
        self._en_curso: dict[Hashable, threading.Lock] = {}
        self._lock = threading.Lock()

    def _vigente(self, clave: Hashable) -> tuple[bool, float | None]:
        entrada = self._valores.get(clave)
        if entrada is not None and entrada[0] > self._reloj():
            return True, entrada[1]
        return False, None

    def obtener(self, clave: Hashable, calcular: Callable[[], float | None]) -> float | None:
        with self._lock:
            hay, valor = self._vigente(clave)
            if hay:
                return valor
            lock_clave = self._en_curso.setdefault(clave, threading.Lock())
        with lock_clave:
            with self._lock:
                # Otro pedido pudo haberlo calculado mientras esperábamos.
                hay, valor = self._vigente(clave)
                if hay:
                    return valor
            valor = calcular()
            with self._lock:
                ahora = self._reloj()
                self._valores = {c: e for c, e in self._valores.items() if e[0] > ahora}
                self._valores[clave] = (ahora + self._ttl, valor)
                self._en_curso.pop(clave, None)
            return valor

    def limpiar(self) -> None:
        with self._lock:
            self._valores.clear()
            self._en_curso.clear()


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

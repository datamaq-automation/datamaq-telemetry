"""src/domain/telemetria/servicios/alcance_tiempo_real.py — A qué medidores renovar el modo de tiempo real.

El modo de tiempo real (`realtime_sync_mode`) solo sirve para quien está mirando en vivo. Se renueva para los
medidores de las organizaciones con un cliente WebSocket conectado, y solo si el medidor publicó hace poco:
uno caído no responde, y mandarle un comando cada 75 s solo llena el journal.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

VENTANA_RECEPCION_RECIENTE_S: int = 600
"""`visto_por_ultima_vez` se actualiza como mucho cada 60 s mientras el medidor publica: 10 min es margen de sobra."""


@dataclass(frozen=True)
class AlcanceTiempoReal:
    """Organizaciones cuyos medidores alguien está mirando en vivo.

    `todas` es True si hay un superadmin conectado: ve todos los medidores, incluso los que no tienen planta.
    """

    todas: bool
    organizaciones: frozenset[str]

    @property
    def vacio(self) -> bool:
        return not self.todas and not self.organizaciones

    def cubre(self, otro: "AlcanceTiempoReal") -> bool:
        if self.todas:
            return True
        if otro.todas:
            return False
        return otro.organizaciones <= self.organizaciones


def alcance_de_clientes(clientes: Iterable[tuple[bool, str | None]]) -> AlcanceTiempoReal:
    """Alcance a partir de pares `(es_superadmin, organizacion_id)` de los clientes conectados.

    Un cliente que no es superadmin y no tiene organización no aporta nada: tampoco recibe eventos
    (`debe_recibir_evento`).
    """
    organizaciones: set[str] = set()
    for es_superadmin, organizacion_id in clientes:
        if es_superadmin:
            return AlcanceTiempoReal(todas=True, organizaciones=frozenset())
        if organizacion_id:
            organizaciones.add(organizacion_id)
    return AlcanceTiempoReal(todas=False, organizaciones=frozenset(organizaciones))


def publico_recientemente(
    visto_por_ultima_vez: datetime | None,
    ahora: datetime,
    ventana_s: int = VENTANA_RECEPCION_RECIENTE_S,
) -> bool:
    if visto_por_ultima_vez is None:
        return False
    return (ahora - visto_por_ultima_vez).total_seconds() <= ventana_s

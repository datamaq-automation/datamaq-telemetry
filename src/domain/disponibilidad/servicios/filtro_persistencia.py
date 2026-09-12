"""src/domain/disponibilidad/servicios/filtro_persistencia.py."""
import threading
from datetime import datetime
from typing import Any

from src.domain.disponibilidad.value_objects import EstadoMaquina


class FiltroPersistenciaEstadoService:
    """Exige que un cambio de estado (marcha↔parada) persista antes de confirmarlo.

    Generaliza para disponibilidad la misma idea anti-transitorios de
    `src.domain.telemetria.services.FiltroPersistenciaTemporalService` (evitar que un
    solo pico o dip de potencia dispare un evento), pero parametrizada por máquina:
    cada `Maquina` define su propia ventana de persistencia
    (`ventana_persistencia_lecturas` / `ventana_persistencia_segundos`).
    Thread-safe vía `threading.Lock`.
    """

    def __init__(self) -> None:
        self._pendientes: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def confirmar_cambio(
        self,
        maquina_id: str,
        estado_confirmado: EstadoMaquina | None,
        estado_candidato: EstadoMaquina,
        min_lecturas: int,
        min_segundos: float,
        ahora: datetime,
    ) -> bool:
        """`True` si `estado_candidato` debe reemplazar a `estado_confirmado` ahora."""
        with self._lock:
            if estado_confirmado == estado_candidato:
                self._pendientes.pop(maquina_id, None)
                return False

            pendiente = self._pendientes.get(maquina_id)
            if pendiente is None or pendiente["estado"] != estado_candidato:
                self._pendientes[maquina_id] = {"estado": estado_candidato, "conteo": 1, "desde": ahora}
                return min_lecturas <= 1

            pendiente["conteo"] += 1
            delta_seg = (ahora - pendiente["desde"]).total_seconds()
            if pendiente["conteo"] >= min_lecturas or delta_seg >= min_segundos:
                self._pendientes.pop(maquina_id, None)
                return True
            return False

    def limpiar(self) -> None:
        with self._lock:
            self._pendientes.clear()

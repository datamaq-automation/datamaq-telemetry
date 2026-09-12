"""src/domain/telemetria/servicios/persistencia_alertas.py."""
import threading
from datetime import datetime, timezone
from typing import Any

from src.domain.telemetria.entities import AlertaDispositivo
from src.domain.telemetria.value_objects import SeveridadAlerta


class FiltroPersistenciaTemporalService:
    """Filtro de persistencia temporal para evitar falsos positivos por transitorios (anti-alert fatigue).

    Una condición de subtensión o sobretensión solo debe disparar una AlertaDispositivo
    si persiste durante al menos `min_lecturas` consecutivas o `min_segundos` continuos.
    Thread-safe vía `threading.Lock`.
    """

    def __init__(self, min_lecturas: int = 2, min_segundos: float = 3.0):
        self._min_lecturas = min_lecturas
        self._min_segundos = min_segundos
        self._estados: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def procesar_alerta(
        self,
        dispositivo_id: str,
        alerta: AlertaDispositivo | None,
        categoria: str | None = None,
        ahora: datetime | None = None,
    ) -> AlertaDispositivo | None:
        """Evalúa si la anomalía cumple con el criterio de persistencia temporal.

        - Si `alerta` es None: la condición para esa `categoria` se normalizó; se resetea el estado correspondiente.
        - Si `alerta` es anómala:
            * 1ra lectura: se registra el inicio del evento; se retorna None (posible transitorio <2s).
            * 2da+ lecturas consecutivas (o delta_t >= min_segundos): se confirma la alerta y se retorna.
            * Episodio activo ya disparado: retorna None para evitar spam de alertas idénticas continuas,
              salvo que la severidad haya escalado a CRITICAL.
        """
        if ahora is None:
            ahora = alerta.disparada_en if alerta and alerta.disparada_en else datetime.now(timezone.utc)

        with self._lock:
            if alerta is None:
                if categoria:
                    if categoria.upper() in ("TENSION", "SUMINISTRO"):
                        self._estados.pop(f"{dispositivo_id}:BAJA_TENSION", None)
                        self._estados.pop(f"{dispositivo_id}:SOBRETENSION", None)
                        self._estados.pop(f"{dispositivo_id}:FALTA_FASE", None)
                    else:
                        self._estados.pop(f"{dispositivo_id}:{categoria}", None)
                else:
                    prefijo = f"{dispositivo_id}:"
                    claves = [k for k in self._estados if k == dispositivo_id or k.startswith(prefijo)]
                    for k in claves:
                        self._estados.pop(k, None)
                return None

            clave = f"{dispositivo_id}:{alerta.tipo_alerta}"
            # Si cambió el tipo de anomalía de tensión/suministro, limpiar los contrarios
            if alerta.tipo_alerta == "BAJA_TENSION":
                self._estados.pop(f"{dispositivo_id}:SOBRETENSION", None)
                self._estados.pop(f"{dispositivo_id}:FALTA_FASE", None)
            elif alerta.tipo_alerta == "SOBRETENSION":
                self._estados.pop(f"{dispositivo_id}:BAJA_TENSION", None)
                self._estados.pop(f"{dispositivo_id}:FALTA_FASE", None)
            elif alerta.tipo_alerta == "FALTA_FASE":
                self._estados.pop(f"{dispositivo_id}:BAJA_TENSION", None)
                self._estados.pop(f"{dispositivo_id}:SOBRETENSION", None)

            estado = self._estados.get(clave)

            if estado is None:
                self._estados[clave] = {
                    "conteo": 1,
                    "primer_registro": ahora,
                    "ultimo_registro": ahora,
                    "disparada": False,
                    "severidad_disparada": None,
                }
                if self._min_lecturas <= 1:
                    self._estados[clave]["disparada"] = True
                    self._estados[clave]["severidad_disparada"] = alerta.severidad
                    return alerta
                return None

            estado["conteo"] += 1
            estado["ultimo_registro"] = ahora
            delta_seg = (ahora - estado["primer_registro"]).total_seconds()
            cumple_persistencia = (estado["conteo"] >= self._min_lecturas) or (delta_seg >= self._min_segundos)

            if not cumple_persistencia:
                return None

            if not estado["disparada"]:
                estado["disparada"] = True
                estado["severidad_disparada"] = alerta.severidad
                alerta.disparada_en = estado["primer_registro"]
                return alerta

            # Si ya fue disparada previamente en este episodio, solo permitir re-disparo si escaló a CRITICAL
            if (
                estado["severidad_disparada"] != SeveridadAlerta.CRITICAL
                and alerta.severidad == SeveridadAlerta.CRITICAL
            ):
                estado["severidad_disparada"] = SeveridadAlerta.CRITICAL
                return alerta

            return None

    def limpiar(self) -> None:
        """Vacía el registro de estados de persistencia."""
        with self._lock:
            self._estados.clear()

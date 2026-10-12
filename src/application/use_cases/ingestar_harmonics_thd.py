"""src/application/use_cases/ingestar_harmonics_thd.py — THDv y THDi por fase desde el topic /harmonics.

/harmonics llega en un mensaje distinto al de /inst. /inst solo persiste una fila cada
granularidad_segundos, así que el THD se asocia a la fila persistida más reciente del mismo dispositivo
dentro de la ventana granularidad + MARGEN_VENTANA_THD_S. Ver tests/unit/test_ingesta_harmonics.py.
"""

from datetime import datetime
from typing import Any

from src.domain.telemetria.ports import RepositorioTelemetriaPort
from src.domain.telemetria.servicios.harmonics_thd import parsear_thd_harmonics

MARGEN_VENTANA_THD_S: int = 60


def ventana_thd_s(granularidad_segundos: int) -> int:
    """Ventana para unir /harmonics con la fila persistida de /inst.

    Por diseño: la fila elegida puede tener hasta `granularidad_segundos + MARGEN_VENTANA_THD_S` de
    antigüedad respecto del instante en que se midió el THD. Si la carga cambió en ese lapso,
    `thd_i_fiable` (calculado con la corriente de esa fila) puede quedar mal clasificado. Salvedad conocida.
    """
    return granularidad_segundos + MARGEN_VENTANA_THD_S


def claves_primer_nivel(payload: object) -> list[str]:
    """Claves de primer nivel del payload, sin valores: alcanzan para contrastar el formato del firmware
    contra `parsear_thd_harmonics` sin volcar el payload completo al journal."""
    if not isinstance(payload, dict):
        return [f"<{type(payload).__name__}>"]
    return sorted(str(clave) for clave in payload)


class IngestarHarmonicsThdUseCase:
    def __init__(
        self,
        repo_telemetria: RepositorioTelemetriaPort,
        granularidad_segundos: int,
        logger: Any | None = None,
    ) -> None:
        self._repo = repo_telemetria
        self._ventana_s = ventana_thd_s(granularidad_segundos)
        self._logger = logger

    def ejecutar(self, dispositivo_id: str, payload: dict[str, Any], momento: datetime) -> bool:
        thd = parsear_thd_harmonics(payload)
        if not thd:
            if self._logger:
                self._logger.info(
                    "harmonics_sin_thd_valido",
                    dispositivo_id=dispositivo_id,
                    motivo="payload_sin_thd_parseable",
                    claves_payload=claves_primer_nivel(payload),
                )
            return False
        guardado = self._repo.actualizar_thd_instantanea(dispositivo_id, momento, self._ventana_s, thd)
        if not guardado and self._logger:
            self._logger.info(
                "harmonics_sin_fila_en_ventana",
                dispositivo_id=dispositivo_id,
                motivo="sin_fila_persistida_en_ventana",
                ventana_s=self._ventana_s,
            )
        return guardado

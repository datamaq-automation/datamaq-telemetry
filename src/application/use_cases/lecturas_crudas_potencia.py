"""src/application/use_cases/lecturas_crudas_potencia.py — muestras crudas de potencia para el histórico de nodo.

Decisión 2026-10-11: el bloque de 15 min se arma desde muestras crudas (promedio de sus sub-bloques de 5 min y
pico de muestras), y el piso del plan se aplica al intervalo de salida, no al de muestreo. Por eso esta ruta no
pasa por ``listar_instantaneas`` (que agrega al piso del plan) ni construye un DTO de analítica por muestra.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from src.application.dtos.telemetria_dto import LecturaInstantaneaDTO

if TYPE_CHECKING:
    from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase

FilaPotencia = tuple[datetime, float | None, float | None]


class LecturasCrudasPotencia:
    """Muestras como ``(registrado_en, P_W, Q_VAR)``, con el corte de retención y el buffer en vivo del caso de uso."""

    def __init__(self, consulta: "ConsultarTelemetriaUseCase") -> None:
        self._consulta = consulta

    def intervalo_minimo_segundos(self, id_o_uid: str) -> int:
        """Piso de granularidad del plan del dispositivo (0 en PRO, 900 s en Free)."""
        c = self._consulta
        return c._obtener_contexto_suscripcion(c._resolver_dispositivo(id_o_uid))[3]

    def listar(
        self,
        id_o_uid: str,
        limite: int,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> list[FilaPotencia]:
        c = self._consulta
        dev = c._resolver_dispositivo(id_o_uid)
        desde_efectivo = c._acotar_fecha_desde(dev, desde)
        if hasta is not None and hasta < desde_efectivo:
            return []
        filas: list[FilaPotencia] = [
            (
                item.registrado_en,
                item.potencia_activa_total.vatios if item.potencia_activa_total else None,
                item.potencia_reactiva_total.var if item.potencia_reactiva_total else None,
            )
            for item in c.repo_telemetria.listar_instantaneas(dev.id, limite, desde_efectivo, hasta)
        ]
        # Margen 0: el buffer aplica con el throttle de persistencia (300 s), como en listar_instantaneas.
        if not c.buffer_en_vivo or not c._buffer_aplica(hasta, 0):
            return filas
        vistos = {registrado for registrado, _, _ in filas}
        for dato in c.buffer_en_vivo.obtener(dev.id):
            dto = LecturaInstantaneaDTO.model_validate(dato)
            if dto.registrado_en in vistos or (hasta is not None and dto.registrado_en > hasta):
                continue
            filas.append((dto.registrado_en, dto.potencia_activa_total_W, dto.potencia_reactiva_total_VAR))
        return filas

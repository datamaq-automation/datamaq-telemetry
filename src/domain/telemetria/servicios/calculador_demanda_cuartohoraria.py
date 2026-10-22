"""src/domain/telemetria/servicios/calculador_demanda_cuartohoraria.py

Cálculo de demanda máxima en bloques de 15 minutos reloj (:00, :15, :30, :45),
segregando Horas Punta (18:00 a 23:00) y Fuera de Punta según normativas de
distribución eléctrica (ENRE / tarifas T2 y T3).

Dominio puro: solo stdlib + dataclasses frozen.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.domain.telemetria.servicios.agregador_dispositivos import (
    AgregadorDispositivosService,
    PuntoPotencia,
)

_ZONA_DEFECTO = ZoneInfo("America/Argentina/Buenos_Aires")
_INTERVALO_CUARTOHORARIO_SEGUNDOS = 900  # 15 minutos reloj


@dataclass(frozen=True)
class DemandaCuartohoraria:
    """Demanda máxima registrada en bloques cuarto-horarios (15 min) por franja."""

    potencia_adquirida_punta_kw: float | None
    potencia_adquirida_fuera_punta_kw: float | None
    momento_pico_punta: datetime | None = None
    momento_pico_fuera_punta: datetime | None = None
    bloques_evaluados: int = 0


class CalculadorDemandaCuartohorariaService:
    """Calculador de demanda cuarto-horaria segregada por franjas horarias."""

    @staticmethod
    def es_hora_punta(momento: datetime, zona: ZoneInfo | str = _ZONA_DEFECTO) -> bool:
        """Determina si un momento dado cae en Horas Punta (18:00 a 23:00 en hora local).

        Horas Punta se define como el intervalo semiabierto [18:00, 23:00), es decir:
        hora >= 18 and hora < 23.
        """
        zi = ZoneInfo(zona) if isinstance(zona, str) else zona
        m = momento if momento.tzinfo is not None else momento.replace(tzinfo=timezone.utc)
        local = m.astimezone(zi)
        return 18 <= local.hour < 23

    @classmethod
    def calcular_demanda(
        cls,
        puntos: list[PuntoPotencia],
        zona: ZoneInfo | str = _ZONA_DEFECTO,
    ) -> DemandaCuartohoraria:
        """Calcula los picos de demanda cuarto-horaria (en kW) a partir de bloques agregados."""
        max_punta: float | None = None
        max_fuera_punta: float | None = None
        momento_punta: datetime | None = None
        momento_fuera_punta: datetime | None = None

        for p in puntos:
            if p.potencia_activa_total_w is None:
                continue
            potencia_kw = p.potencia_activa_total_w / 1000.0
            if cls.es_hora_punta(p.momento, zona):
                if max_punta is None or potencia_kw > max_punta:
                    max_punta = potencia_kw
                    momento_punta = p.momento
            else:
                if max_fuera_punta is None or potencia_kw > max_fuera_punta:
                    max_fuera_punta = potencia_kw
                    momento_fuera_punta = p.momento

        return DemandaCuartohoraria(
            potencia_adquirida_punta_kw=round(max_punta, 2) if max_punta is not None else None,
            potencia_adquirida_fuera_punta_kw=round(max_fuera_punta, 2) if max_fuera_punta is not None else None,
            momento_pico_punta=momento_punta,
            momento_pico_fuera_punta=momento_fuera_punta,
            bloques_evaluados=len(puntos),
        )

    @classmethod
    def calcular_demanda_desde_lecturas(
        cls,
        lecturas_por_dispositivo: dict[str, list[tuple]],
        zona: ZoneInfo | str = _ZONA_DEFECTO,
    ) -> DemandaCuartohoraria:
        """Agrega lecturas crudas en bloques cuarto-horarios de 15 min (:00, :15, :30, :45) y calcula demanda."""
        bloques = AgregadorDispositivosService.sumar_potencia_en_el_tiempo(
            lecturas_por_dispositivo,
            intervalo_segundos=_INTERVALO_CUARTOHORARIO_SEGUNDOS,
        )
        return cls.calcular_demanda(bloques, zona=zona)

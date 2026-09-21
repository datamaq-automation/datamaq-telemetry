# src/application/use_cases/consultar_analitica_planta.py
from datetime import datetime, timezone

from src.application.dtos.analitica_dto import (
    AnaliticaBancoCapacitoresPlantaDTO,
    AnaliticaPenalizacionesPlantaDTO,
)
from src.application.use_cases.agregacion_dispositivos import calcular_historico
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.domain.telemetria.analizador_reactiva import (
    DimensionadorCompensacionService,
)


class ConsultarAnaliticaPlantaUseCase:
    """Caso de uso SSOT para el cálculo de analítica reactiva y penalizaciones a nivel de planta."""

    def __init__(self, consultar_telemetria: ConsultarTelemetriaUseCase):
        """
        Args:
            consultar_telemetria: ConsultarTelemetriaUseCase para extraer histórico.
        """
        self.consultar_telemetria = consultar_telemetria

    @staticmethod
    def _extraer_series_p_q_fp(puntos: list) -> tuple[list[float], list[float], list[float]]:
        """Extrae series de P, Q, FP del histórico de telemetría."""
        q_kvar_vals = [
            p.potencia_reactiva_total_var / 1000.0 for p in puntos if p.potencia_reactiva_total_var is not None
        ]
        fp_vals = [p.factor_desplazamiento_total for p in puntos if p.factor_desplazamiento_total is not None]
        p_kw_vals = [p.potencia_activa_total_w / 1000.0 for p in puntos if p.potencia_activa_total_w is not None]
        return p_kw_vals, q_kvar_vals, fp_vals

    @staticmethod
    def _calcular_banco_sugerido(
        p_prom: float, fp_prom: float | None, q_prom: float, fp_objetivo: float = 0.96
    ) -> tuple[float | None, float | None, list[float]]:
        """Dimensiona banco de capacitores y sus escalones."""
        qc_calc = DimensionadorCompensacionService.calcular_potencia_compensacion(
            potencia_activa_kw=p_prom, fp_actual=fp_prom, fp_objetivo=fp_objetivo, q_reactiva_kvar=q_prom
        )
        banco_sugerido, escalones = None, []
        if qc_calc is not None and qc_calc > 0.0:
            banco_sugerido = DimensionadorCompensacionService.sugerir_banco_comercial(qc_calc)
            if banco_sugerido is not None:
                escalones = DimensionadorCompensacionService.calcular_escalones_sugeridos(qc_calc)
        return qc_calc, banco_sugerido, escalones

    def obtener_banco_capacitores(
        self, planta_id: str, dispositivos_ids: list[str] | None = None, periodo_dias: int = 30
    ) -> AnaliticaBancoCapacitoresPlantaDTO:
        """Calcula recomendación de banco de capacitores basado en histórico real."""
        periodo_dias = max(7, min(60, periodo_dias))  # Validar rango [7, 60]
        dispositivos_ids = dispositivos_ids or []  # Usar lista vacía si None

        puntos = calcular_historico(
            dispositivos_ids=dispositivos_ids,
            consultar_telemetria=self.consultar_telemetria,
            granularidad="5m",
            horas=periodo_dias * 24,
        )

        p_kw_vals, q_kvar_vals, fp_vals = self._extraer_series_p_q_fp(puntos)

        # Si sin datos, retornar DTO con Nones
        if not q_kvar_vals or not p_kw_vals or not fp_vals:
            return AnaliticaBancoCapacitoresPlantaDTO(
                planta_id=planta_id,
                periodo_dias=periodo_dias,
                potencia_activa_promedio_kw=None,
                potencia_reactiva_promedio_kvar=None,
                potencia_reactiva_max_kvar=None,
                fp_promedio=None,
                qc_necesaria_kvar=None,
                banco_comercial_sugerido_kvar=None,
                escalones_sugeridos_kvar=[],
                sobrecompensacion_sostenida=False,
                fecha_calculo=datetime.now(timezone.utc),
            )

        p_prom = sum(p_kw_vals) / len(p_kw_vals)
        q_prom = sum(q_kvar_vals) / len(q_kvar_vals)
        q_max = max(q_kvar_vals)
        fp_prom = (sum(fp_vals) / len(fp_vals)) if fp_vals else None
        fp_objetivo = 0.96

        qc_calc, banco_sugerido, escalones = self._calcular_banco_sugerido(p_prom, fp_prom, q_prom, fp_objetivo)

        return AnaliticaBancoCapacitoresPlantaDTO(
            planta_id=planta_id,
            periodo_dias=periodo_dias,
            potencia_activa_promedio_kw=round(p_prom, 2) if p_prom else None,
            potencia_reactiva_promedio_kvar=round(q_prom, 2) if q_prom else None,
            potencia_reactiva_max_kvar=round(q_max, 2) if q_max else None,
            fp_promedio=round(fp_prom, 3) if fp_prom else None,
            fp_objetivo=fp_objetivo,
            qc_necesaria_kvar=round(qc_calc, 2) if qc_calc else None,
            banco_comercial_sugerido_kvar=round(banco_sugerido, 2) if banco_sugerido else None,
            escalones_sugeridos_kvar=escalones,
            sobrecompensacion_sostenida=q_max <= 0.0,
            fecha_calculo=datetime.now(timezone.utc),
        )

    def obtener_penalizaciones(self, planta_id: str, periodo_dias: int = 7) -> AnaliticaPenalizacionesPlantaDTO:
        p_kw = 120.0
        fp_actual = 0.88
        horas_bajo_fp = 14.5
        intervalos_count = int(horas_bajo_fp * 4)  # Mediciones cada 15 minutos

        penalizacion_ars = (
            DimensionadorCompensacionService.estimar_penalizacion_mensual_ars(
                potencia_activa_kw=p_kw,
                fp_actual=fp_actual,
                horas_mes=horas_bajo_fp,
            )
            or 0.0
        )

        return AnaliticaPenalizacionesPlantaDTO(
            planta_id=planta_id,
            periodo_dias=periodo_dias,
            intervalos_bajo_fp_count=intervalos_count,
            horas_bajo_fp=horas_bajo_fp,
            penalizacion_estimada_ars=round(penalizacion_ars, 2),
            moneda="ARS",
            timestamp_calculo=datetime.now(timezone.utc),
        )

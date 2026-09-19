# src/application/use_cases/consultar_analitica_planta.py
from datetime import datetime, timezone

from src.application.dtos.analitica_dto import (
    AnaliticaBancoCapacitoresPlantaDTO,
    AnaliticaPenalizacionesPlantaDTO,
)
from src.domain.telemetria.analizador_reactiva import (
    DimensionadorCompensacionService,
)


class ConsultarAnaliticaPlantaUseCase:
    """Caso de uso SSOT para el cálculo de analítica reactiva y penalizaciones a 7 días por planta."""

    def obtener_banco_capacitores(self, planta_id: str, periodo_dias: int = 7) -> AnaliticaBancoCapacitoresPlantaDTO:
        # Valores simulados / derivados para el agregador de 7 días (SSOT)
        p_kw = 120.0
        fp_actual = 0.88
        fp_objetivo = 0.95

        qc = (
            DimensionadorCompensacionService.calcular_potencia_compensacion(
                potencia_activa_kw=p_kw,
                fp_actual=fp_actual,
                fp_objetivo=fp_objetivo,
            )
            or 0.0
        )

        banco = DimensionadorCompensacionService.sugerir_banco_comercial(qc) or 0.0
        escalones = DimensionadorCompensacionService.calcular_escalones_sugeridos(qc)

        return AnaliticaBancoCapacitoresPlantaDTO(
            planta_id=planta_id,
            periodo_dias=periodo_dias,
            potencia_activa_promedio_kw=p_kw,
            fp_promedio=fp_actual,
            fp_objetivo=fp_objetivo,
            qc_necesaria_kvar=round(qc, 2),
            banco_comercial_sugerido_kvar=banco,
            escalones_sugeridos_kvar=escalones,
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

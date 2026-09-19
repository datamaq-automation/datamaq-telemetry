"""src/domain/produccion/servicios/calculador_enpi_hibrido.py — Servicio de cálculo de SEC híbrido."""

from datetime import datetime

from src.domain.produccion.entities import (
    ConfiguracionMedicionMaquina,
    ModoMedicion,
    ResultadoSecHibrido,
)


class CalculadorEnpiHibridoService:
    """Calculador de desempeño energético específico adaptativo (ISO 50001 §6.5 / ISO 50006)."""

    @classmethod
    def calcular(
        cls,
        config: ConfiguracionMedicionMaquina,
        periodo_inicio: datetime,
        periodo_fin: datetime,
        energia_kwh: float,
        unidades_produccion: float,
        horas_activas_proceso: float,
        potencia_media_kw: float | None = None,
        factor_carga_estimado: float = 0.75,
    ) -> ResultadoSecHibrido:
        """Calcula el SEC y desglosa consumo productivo vs no productivo según topología."""
        sec = round(energia_kwh / unidades_produccion, 6) if unidades_produccion > 0 else None

        if config.es_medicion_dedicada:
            potencia_med = (
                potencia_media_kw if potencia_media_kw is not None else (energia_kwh / max(horas_activas_proceso, 1e-3))
            )
            energia_prod = round(potencia_med * horas_activas_proceso, 3)
            energia_prod = min(energia_prod, energia_kwh)
            energia_no_prod = round(max(0.0, energia_kwh - energia_prod), 3)
            ratio_desperdicio = round((energia_no_prod / energia_kwh) * 100.0, 2) if energia_kwh > 0 else 0.0
            detalle = "Medición directa en seccional/CCM de máquina"

            return ResultadoSecHibrido(
                maquina_id=config.maquina_id,
                modo_medicion=ModoMedicion.DEDICADA_SECCIONAL,
                periodo_inicio=periodo_inicio,
                periodo_fin=periodo_fin,
                energia_total_kwh=round(energia_kwh, 3),
                unidades_procesadas=unidades_produccion,
                sec_kwh_por_unidad=sec,
                energia_productiva_kwh=energia_prod,
                energia_no_productiva_kwh=energia_no_prod,
                ratio_desperdicio_pct=ratio_desperdicio,
                detalle_estimacion=detalle,
            )

        potencia_estimada_kw = config.potencia_nominal_kw * factor_carga_estimado
        energia_prod_est = round(potencia_estimada_kw * horas_activas_proceso, 3)
        energia_prod_est = min(energia_prod_est, energia_kwh)
        energia_resto_planta = round(max(0.0, energia_kwh - energia_prod_est), 3)

        sec_maquina_est = round(energia_prod_est / unidades_produccion, 6) if unidades_produccion > 0 else None
        ratio_desperdicio = round((energia_resto_planta / energia_kwh) * 100.0, 2) if energia_kwh > 0 else 0.0
        detalle = (
            f"Desagregación asistida en TGBT: potencia nominal={config.potencia_nominal_kw}kW, "
            f"LF={factor_carga_estimado}, horas_activas={horas_activas_proceso}h"
        )

        return ResultadoSecHibrido(
            maquina_id=config.maquina_id,
            modo_medicion=ModoMedicion.AGREGADA_TGBT,
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            energia_total_kwh=round(energia_kwh, 3),
            unidades_procesadas=unidades_produccion,
            sec_kwh_por_unidad=sec_maquina_est,
            energia_productiva_kwh=energia_prod_est,
            energia_no_productiva_kwh=energia_resto_planta,
            ratio_desperdicio_pct=ratio_desperdicio,
            detalle_estimacion=detalle,
        )

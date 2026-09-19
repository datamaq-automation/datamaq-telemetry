"""src/application/mappers/produccion_mapper.py — Mappers para DTOs de producción."""

from src.application.dtos.produccion_dto import (
    LecturaProcesoResponseDTO,
    ResultadoSecResponseDTO,
)
from src.domain.produccion.entities import ResultadoSecHibrido
from src.domain.produccion.value_objects import LecturaVariableProceso


def lectura_to_dto(lectura: LecturaVariableProceso, maquina_id: str) -> LecturaProcesoResponseDTO:
    """Mapea una entidad LecturaVariableProceso a LecturaProcesoResponseDTO."""
    return LecturaProcesoResponseDTO(
        maquinaId=maquina_id,
        momento=lectura.momento.isoformat(),
        variableTipo=lectura.variable_tipo.value,
        deltaValor=lectura.delta_valor,
        valorAcumulado=lectura.valor_acumulado,
    )


def resultado_sec_to_dto(resultado: ResultadoSecHibrido) -> ResultadoSecResponseDTO:
    """Mapea un ResultadoSecHibrido a ResultadoSecResponseDTO."""
    return ResultadoSecResponseDTO(
        maquinaId=resultado.maquina_id,
        modoMedicion=resultado.modo_medicion.value,
        periodoInicio=resultado.periodo_inicio.isoformat(),
        periodoFin=resultado.periodo_fin.isoformat(),
        energiaTotalKwh=resultado.energia_total_kwh,
        unidadesProcesadas=resultado.unidades_procesadas,
        secKwhPorUnidad=resultado.sec_kwh_por_unidad,
        energiaProductivaKwh=resultado.energia_productiva_kwh,
        energiaNoProductivaKwh=resultado.energia_no_productiva_kwh,
        ratioDesperdicioPct=resultado.ratio_desperdicio_pct,
        detalleEstimacion=resultado.detalle_estimacion,
    )

"""src/application/dtos/produccion_dto.py — DTOs para sensórica de proceso y EnPI."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.domain.produccion.value_objects import TipoVariableProceso


class LecturaProcesoRequestDTO(BaseModel):
    maquina_id: str = Field(alias="maquinaId")
    momento: datetime
    variable_tipo: TipoVariableProceso = Field(alias="variableTipo")
    delta_valor: float = Field(alias="deltaValor")
    valor_acumulado: float = Field(alias="valorAcumulado")

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class LecturaProcesoResponseDTO(BaseModel):
    maquina_id: str = Field(alias="maquinaId")
    momento: str
    variable_tipo: str = Field(alias="variableTipo")
    delta_valor: float = Field(alias="deltaValor")
    valor_acumulado: float = Field(alias="valorAcumulado")

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class CalcularSecRequestDTO(BaseModel):
    maquina_id: str = Field(alias="maquinaId")
    periodo_inicio: datetime = Field(alias="periodoInicio")
    periodo_fin: datetime = Field(alias="periodoFin")
    energia_kwh: float = Field(alias="energiaKwh")
    unidades_produccion: float = Field(alias="unidadesProduccion")
    horas_activas_proceso: float = Field(alias="horasActivasProceso")
    potencia_media_kw: float | None = Field(default=None, alias="potenciaMediaKw")

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class ResultadoSecResponseDTO(BaseModel):
    maquina_id: str = Field(alias="maquinaId")
    modo_medicion: str = Field(alias="modoMedicion")
    periodo_inicio: str = Field(alias="periodoInicio")
    periodo_fin: str = Field(alias="periodoFin")
    energia_total_kwh: float = Field(alias="energiaTotalKwh")
    unidades_procesadas: float = Field(alias="unidadesProcesadas")
    sec_kwh_por_unidad: float | None = Field(default=None, alias="secKwhPorUnidad")
    energia_productiva_kwh: float = Field(alias="energiaProductivaKwh")
    energia_no_productiva_kwh: float = Field(alias="energiaNoProductivaKwh")
    ratio_desperdicio_pct: float = Field(alias="ratioDesperdicioPct")
    detalle_estimacion: str | None = Field(default=None, alias="detalleEstimacion")

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

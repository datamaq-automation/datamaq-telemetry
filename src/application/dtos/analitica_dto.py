# src/application/dtos/analitica_dto.py
from datetime import datetime

from pydantic import BaseModel, Field


class AnaliticaBancoCapacitoresPlantaDTO(BaseModel):
    planta_id: str = Field(..., description="Identificador único de la planta")
    periodo_dias: int = Field(default=30, description="Ventana de análisis en días (ISO 50001: mínimo 30)")
    periodo_dias_analizado: int = Field(
        default=30, description="Días analizados en la ventana histórica (ISO 50001: mínimo 30)"
    )
    potencia_activa_promedio_kw: float | None = Field(..., description="Potencia activa promedio P (kW)")
    potencia_reactiva_promedio_kvar: float | None = Field(
        default=None, description="Potencia reactiva promedio Q (kVAr)"
    )
    potencia_reactiva_max_kvar: float | None = Field(
        default=None, description="Potencia reactiva máxima Q_max (kVAr) en el período"
    )
    fp_promedio: float | None = Field(default=None, description="Factor de potencia promedio registrado")
    fp_objetivo: float = Field(default=0.96, description="Factor de potencia objetivo ENRE (0.96)")
    qc_necesaria_kvar: float | None = Field(
        default=None, description="Potencia reactiva de compensación necesaria Qc (kVAr)"
    )
    banco_comercial_sugerido_kvar: float | None = Field(
        default=None, description="Capacidad del banco de capacitores comercial sugerido (kVAr)"
    )
    escalones_sugeridos_kvar: list[float] = Field(
        default_factory=list, description="Desglose modular de escalones sugeridos"
    )
    sobrecompensacion_sostenida: bool = Field(
        default=False, description="True si Q_max <= 0 (planta en régimen capacitivo durante todo el período)"
    )
    razon_no_recomendacion: str | None = Field(
        default=None,
        description="Razón por la que no se recomienda banco (ej. 'FP superior a 0.95', 'Período insuficiente')",
    )
    pendiente_30_dias: bool = Field(
        default=False, description="True si período < 30 días (en evaluación, falta histórico)"
    )
    fecha_calculo: datetime = Field(..., description="Fecha y hora ISO del cálculo")


class AnaliticaPenalizacionesPlantaDTO(BaseModel):
    planta_id: str = Field(..., description="Identificador único de la planta")
    periodo_dias: int = Field(default=7, description="Ventana de análisis en días")
    disponible: bool = Field(
        default=False, description="False mientras el cálculo real de penalizaciones no esté implementado"
    )
    motivo_no_disponible: str | None = Field(
        default=None, description="Por qué no hay cifra (ej. 'Cálculo no implementado'); None si disponible"
    )
    intervalos_bajo_fp_count: int | None = Field(
        default=None, description="Cantidad de intervalos de medición con FP < 0.95; None si no disponible"
    )
    horas_bajo_fp: float | None = Field(
        default=None, description="Horas acumuladas con bajo factor de potencia; None si no disponible"
    )
    penalizacion_estimada_ars: float | None = Field(
        default=None, description="Penalización estimada acumulada en ARS; None si no disponible"
    )
    moneda: str = Field(default="ARS", description="Código de moneda")
    timestamp_calculo: datetime = Field(..., description="Fecha y hora ISO del cálculo")

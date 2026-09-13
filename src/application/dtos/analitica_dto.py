from datetime import datetime

from pydantic import BaseModel, Field


class AnaliticaBancoCapacitoresPlantaDTO(BaseModel):
    planta_id: str = Field(..., description="Identificador único de la planta")
    periodo_dias: int = Field(default=7, description="Ventana de análisis en días")
    potencia_activa_promedio_kw: float = Field(..., description="Potencia activa promedio P (kW)")
    fp_promedio: float = Field(..., description="Factor de potencia promedio registrado")
    fp_objetivo: float = Field(default=0.95, description="Factor de potencia objetivo ENRE")
    qc_necesaria_kvar: float = Field(..., description="Potencia reactiva de compensación necesaria Qc (kVAr)")
    banco_comercial_sugerido_kvar: float = Field(
        ..., description="Capacidad del banco de capacitores comercial sugerido (kVAr)"
    )
    escalones_sugeridos_kvar: list[float] = Field(
        default_factory=list, description="Desglose modular de escalones sugeridos"
    )


class AnaliticaPenalizacionesPlantaDTO(BaseModel):
    planta_id: str = Field(..., description="Identificador único de la planta")
    periodo_dias: int = Field(default=7, description="Ventana de análisis en días")
    intervalos_bajo_fp_count: int = Field(..., description="Cantidad de intervalos de medición con FP < 0.95")
    horas_bajo_fp: float = Field(..., description="Horas acumuladas con bajo factor de potencia")
    penalizacion_estimada_ars: float = Field(..., description="Penalización estimada acumulada en ARS")
    moneda: str = Field(default="ARS", description="Código de moneda")
    timestamp_calculo: datetime = Field(..., description="Fecha y hora ISO del cálculo")

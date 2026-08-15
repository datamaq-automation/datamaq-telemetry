from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.domain.telemetria.value_objects import VisibilidadPlan


class PlanCreateDTO(BaseModel):
    nombre: str
    descripcion: str
    precio_mensual_ars: Decimal
    visibilidad: VisibilidadPlan
    retencion_dias: int
    granularidad_minutos: int
    max_dispositivos: int
    canales_notificacion: list[str]


class PlanResponseDTO(PlanCreateDTO):
    id: str
    creado_en: datetime
    actualizado_en: datetime
    model_config = ConfigDict(from_attributes=True)

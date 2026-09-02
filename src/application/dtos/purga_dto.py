from pydantic import BaseModel, Field

from src.application.dtos.tipos import FechaHoraUTC


class PurgaRequestDTO(BaseModel):
    dias_retencion_override: int | None = Field(default=None, description="Sobrescribir días de retención global")
    corte_hasta: FechaHoraUTC | None = Field(
        default=None, description="Corte por timestamp UTC explícito (purga todo lo anterior)"
    )
    batch_size: int = Field(default=1000, description="Tamaño de lote para borrados por transacción", ge=10, le=10000)


class PurgaResultadoDTO(BaseModel):
    instantaneas_eliminadas: int = 0
    energias_eliminadas: int = 0
    status_logs_eliminados: int = 0
    alertas_resueltas_eliminadas: int = 0
    total_registros_eliminados: int = 0
    duracion_segundos: float = 0.0
    ejecutado_en: FechaHoraUTC

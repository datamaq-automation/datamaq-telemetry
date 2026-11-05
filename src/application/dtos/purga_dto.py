"""src/application/dtos/purga_dto.py."""

from pydantic import BaseModel, Field

from src.application.dtos.tipos import FechaHoraUTC


class PurgaRequestDTO(BaseModel):
    dias_retencion_override: int | None = Field(default=None, description="Sobrescribir días de retención global")
    dias_retencion_instantaneas: int | None = Field(
        default=None, description="Días de retención para telemetría instantánea cruda (default: 45 días)"
    )
    dias_retencion_energia: int | None = Field(
        default=None, description="Días de retención para telemetría acumulada (default: 5 años / 1825 días)"
    )
    corte_hasta: FechaHoraUTC | None = Field(
        default=None, description="Corte por timestamp UTC explícito (purga todo lo anterior)"
    )
    batch_size: int = Field(default=1000, description="Tamaño de lote para borrados por transacción", ge=10, le=50000)


class PurgaResultadoDTO(BaseModel):
    instantaneas_eliminadas: int = 0
    energias_eliminadas: int = 0
    status_logs_eliminados: int = 0
    alertas_resueltas_eliminadas: int = 0
    total_registros_eliminados: int = 0
    duracion_segundos: float = 0.0
    ejecutado_en: FechaHoraUTC
    simulado: bool = Field(default=False, description="true si no se borró nada (solo conteo)")


class PurgaSolicitudDTO(PurgaRequestDTO):
    """Cuerpo de `POST /api/v1/system/purge` (datamaq#119).

    Sin `confirmar` la ruta simula: cuenta lo que borraría y no borra nada.
    `confirmar_retencion_menor` habilita recortar por debajo del piso de retención de una tabla.
    """

    confirmar: bool = Field(default=False, description="true para borrar; false (default) simula")
    confirmar_retencion_menor: bool = Field(
        default=False, description="true para recortar por debajo del piso de retención de alguna tabla"
    )

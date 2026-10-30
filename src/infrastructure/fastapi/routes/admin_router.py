"""src/infrastructure/fastapi/routes/admin_router.py — Router de auditoría y administración."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from src.application.use_cases.consultar_auditoria_cambios_ti import ConsultarAuditoriaCambiosTIUseCase
from src.domain.auth.entities import UsuarioAuth
from src.infrastructure.fastapi.dependencies import get_usuario_actual, requiere_rol_admin
from src.infrastructure.fastapi.dependencies_auditoria_ti import get_consultar_auditoria_cambios_ti


class AuditoriaChangesTIResponseDTO(BaseModel):
    id: int
    device_id: str
    dispositivo_alias: str | None = None
    tipo_cambio: str
    valor_anterior: str | None = None
    valor_nuevo: str | None = None
    motivo: str | None = None
    commit_git: str | None = None
    usuario: str | None = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditoriaChangesTIDetailDTO(AuditoriaChangesTIResponseDTO):
    commit_url: str | None = None
    dispositivo_detalle: dict | None = None


class AuditoriaChangesListResponseDTO(BaseModel):
    total: int
    registros: list[AuditoriaChangesTIResponseDTO]


router = APIRouter(prefix="/api/v1/admin", tags=["Administración"])


@router.get(
    "/auditoria/cambios-ti",
    response_model=AuditoriaChangesListResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Listar cambios de TI auditados",
    dependencies=[Depends(requiere_rol_admin)],
)
async def listar_cambios_ti(
    usuario_actual: Annotated[UsuarioAuth, Depends(get_usuario_actual)],
    auditoria: Annotated[ConsultarAuditoriaCambiosTIUseCase, Depends(get_consultar_auditoria_cambios_ti)],
    dispositivo_id: str | None = Query(None, description="Filtrar por dispositivo_id"),
    tipo_cambio: str | None = Query(None, description="Filtrar por tipo_cambio"),
    desde: datetime | None = Query(None, description="Desde (ISO 8601)"),
    hasta: datetime | None = Query(None, description="Hasta (ISO 8601)"),
) -> AuditoriaChangesListResponseDTO:
    """Listar cambios de TI con filtros opcionales."""
    registros = auditoria.listar(
        dispositivo_id=dispositivo_id,
        tipo_cambio=tipo_cambio,
        desde=desde,
        hasta=hasta,
    )
    return AuditoriaChangesListResponseDTO(
        total=len(registros),
        registros=[AuditoriaChangesTIResponseDTO.model_validate(r) for r in registros],
    )


@router.get(
    "/auditoria/cambios-ti/{cambio_id}",
    response_model=AuditoriaChangesTIDetailDTO,
    status_code=status.HTTP_200_OK,
    summary="Detalle de cambio de TI",
    dependencies=[Depends(requiere_rol_admin)],
)
async def detalle_cambio_ti(
    cambio_id: int,
    usuario_actual: Annotated[UsuarioAuth, Depends(get_usuario_actual)],
    auditoria: Annotated[ConsultarAuditoriaCambiosTIUseCase, Depends(get_consultar_auditoria_cambios_ti)],
) -> AuditoriaChangesTIDetailDTO:
    """Obtener detalles completos de un cambio TI."""
    cambio = auditoria.detalle(cambio_id)
    if cambio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cambio no encontrado")

    commit_url = None
    if cambio["commit_git"]:
        commit_url = f"https://github.com/datamaq-automation/datamaq-data/commit/{cambio['commit_git']}"

    return AuditoriaChangesTIDetailDTO(
        **AuditoriaChangesTIResponseDTO.model_validate(cambio).model_dump(),
        commit_url=commit_url,
        dispositivo_detalle=cambio["dispositivo"],
    )

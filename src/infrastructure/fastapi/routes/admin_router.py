"""src/infrastructure/fastapi/routes/admin_router.py — Router de auditoría y administración."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.auth.entities import UsuarioAuth
from src.infrastructure.fastapi.dependencies import get_usuario_actual, requiere_rol_admin
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.models import AuditoriaChangesTIModel


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
    db: Annotated[Session, Depends(get_db_session)],
    dispositivo_id: str | None = Query(None, description="Filtrar por dispositivo_id"),
    tipo_cambio: str | None = Query(None, description="Filtrar por tipo_cambio"),
    desde: datetime | None = Query(None, description="Desde (ISO 8601)"),
    hasta: datetime | None = Query(None, description="Hasta (ISO 8601)"),
) -> AuditoriaChangesListResponseDTO:
    """Listar cambios de TI con filtros opcionales."""
    query = select(AuditoriaChangesTIModel)

    if dispositivo_id:
        query = query.where(AuditoriaChangesTIModel.device_id == dispositivo_id)
    if tipo_cambio:
        query = query.where(AuditoriaChangesTIModel.tipo_cambio == tipo_cambio)
    if desde:
        query = query.where(AuditoriaChangesTIModel.timestamp >= desde)
    if hasta:
        query = query.where(AuditoriaChangesTIModel.timestamp <= hasta)

    query = query.order_by(AuditoriaChangesTIModel.timestamp.desc())
    registros = db.scalars(query).all()

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
    db: Annotated[Session, Depends(get_db_session)],
) -> AuditoriaChangesTIDetailDTO:
    """Obtener detalles completos de un cambio TI."""
    cambio = db.query(AuditoriaChangesTIModel).filter(AuditoriaChangesTIModel.id == cambio_id).first()
    if not cambio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cambio no encontrado")

    # Construir URL del commit
    commit_url = None
    if cambio.commit_git:
        commit_url = f"https://github.com/datamaq-automation/datamaq-data/commit/{cambio.commit_git}"

    return AuditoriaChangesTIDetailDTO(
        **AuditoriaChangesTIResponseDTO.model_validate(cambio).model_dump(),
        commit_url=commit_url,
        dispositivo_detalle={
            "id": cambio.device_id,
            "alias": cambio.device.name if cambio.device else None,
            "ubicacion": cambio.device.tag_location if cambio.device else None,
            "config_actual": {
                "correccion_angular_fases": cambio.device.ct_phase_angle_offsets if cambio.device else None,
                "fases_con_ti": cambio.device.phases_with_ct if cambio.device else None,
                "invertido": bool(cambio.device.ct_inverted_phases) if cambio.device else False,
            },
        }
        if cambio.device
        else None,
    )

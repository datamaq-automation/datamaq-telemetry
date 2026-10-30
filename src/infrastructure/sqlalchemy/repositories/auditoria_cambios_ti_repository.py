"""src/infrastructure/sqlalchemy/repositories/auditoria_cambios_ti_repository.py."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.telemetria.ports import RepositorioAuditoriaCambiosTIPort
from src.infrastructure.sqlalchemy.models import AuditoriaChangesTIModel


def _a_registro(cambio: AuditoriaChangesTIModel) -> dict[str, Any]:
    return {
        "id": cambio.id,
        "device_id": cambio.device_id,
        "tipo_cambio": cambio.tipo_cambio,
        "valor_anterior": cambio.valor_anterior,
        "valor_nuevo": cambio.valor_nuevo,
        "motivo": cambio.motivo,
        "commit_git": cambio.commit_git,
        "usuario": cambio.usuario,
        "timestamp": cambio.timestamp,
    }


class AuditoriaCambiosTIRepository(RepositorioAuditoriaCambiosTIPort):
    """Implementación SQLAlchemy de la auditoría de cambios de TI."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def listar(
        self,
        dispositivo_id: str | None,
        tipo_cambio: str | None,
        desde: datetime | None,
        hasta: datetime | None,
    ) -> list[dict[str, Any]]:
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
        return [_a_registro(c) for c in self._db.scalars(query).all()]

    def obtener(self, cambio_id: int) -> dict[str, Any] | None:
        cambio = self._db.scalars(
            select(AuditoriaChangesTIModel).where(AuditoriaChangesTIModel.id == cambio_id)
        ).first()
        if cambio is None:
            return None
        registro = _a_registro(cambio)
        dispositivo = cambio.device
        registro["dispositivo"] = (
            {
                "id": cambio.device_id,
                "alias": dispositivo.name,
                "ubicacion": dispositivo.tag_location,
                "config_actual": {
                    "correccion_angular_fases": dispositivo.ct_phase_angle_offsets,
                    "fases_con_ti": dispositivo.phases_with_ct,
                    "invertido": bool(dispositivo.ct_inverted_phases),
                },
            }
            if dispositivo is not None
            else None
        )
        return registro

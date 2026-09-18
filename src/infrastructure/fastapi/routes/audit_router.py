"""src/infrastructure/fastapi/routes/audit_router.py — Router de consulta de registros de auditoría."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.application.dtos.audit_dto import (
    AuditLogDTO,
    CategoriaAuditType,
    ConsultarAuditLogsQueryDTO,
)
from src.application.use_cases.gestionar_auditoria import ConsultarAuditLogsUseCase
from src.infrastructure.fastapi.dependencies import (
    get_consultar_auditoria_use_case,
    requiere_rol_auditor_o_superadmin,
)

router = APIRouter(prefix="/api/v1/audit", tags=["Auditoría"])


@router.get(
    "/logs",
    response_model=list[AuditLogDTO],
    dependencies=[Depends(requiere_rol_auditor_o_superadmin)],
)
def listar_audit_logs(
    use_case: Annotated[ConsultarAuditLogsUseCase, Depends(get_consultar_auditoria_use_case)],
    categoria: CategoriaAuditType | None = None,
    accion: str | None = None,
    actor_usuario_id: str | None = None,
    recurso_tipo: str | None = None,
    recurso_id: str | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    limite: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[AuditLogDTO]:
    """Consulta de registros de auditoría inmutable para supervisión de seguridad y cumplimiento normativo."""
    query = ConsultarAuditLogsQueryDTO(
        categoria=categoria,
        accion=accion,
        actor_usuario_id=actor_usuario_id,
        recurso_tipo=recurso_tipo,
        recurso_id=recurso_id,
        desde=desde,
        hasta=hasta,
        limite=limite,
        offset=offset,
    )
    return use_case.ejecutar(query)

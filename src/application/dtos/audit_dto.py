"""src/application/dtos/audit_dto.py — DTOs de auditoría inmutable."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CategoriaAuditType = Literal["AUTH", "METROLOGIA", "USUARIOS", "SISTEMA"]
ResultadoAuditType = Literal["EXITO", "RECHAZADO", "ERROR"]


class AuditLogDTO(BaseModel):
    """Contrato de lectura de evento de auditoría para la SPA y consumidores API."""

    id: str
    registrado_en: datetime
    actor_email: str | None = None
    actor_ip: str | None = None
    categoria: CategoriaAuditType
    accion: str
    resultado: ResultadoAuditType
    recurso_tipo: str | None = None
    recurso_id: str | None = None
    metadatos: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class RegistrarAuditLogDTO(BaseModel):
    """DTO para solicitar la persistencia de un nuevo evento de auditoría."""

    categoria: CategoriaAuditType
    accion: str
    resultado: ResultadoAuditType
    actor_usuario_id: str | None = None
    actor_email: str | None = None
    actor_ip: str | None = None
    actor_user_agent: str | None = None
    recurso_tipo: str | None = None
    recurso_id: str | None = None
    metadatos: dict[str, Any] | None = None


class ConsultarAuditLogsQueryDTO(BaseModel):
    """Parámetros de filtrado y paginación para consulta de auditoría."""

    categoria: CategoriaAuditType | None = None
    accion: str | None = None
    actor_usuario_id: str | None = None
    recurso_tipo: str | None = None
    recurso_id: str | None = None
    desde: datetime | None = None
    hasta: datetime | None = None
    limite: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

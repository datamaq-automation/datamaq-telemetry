"""src/application/mappers/auditoria_mapper.py — Mappers para entidades y DTOs de auditoría."""

from typing import cast

from src.application.dtos.audit_dto import AuditLogDTO, CategoriaAuditType, ResultadoAuditType
from src.domain.auditoria.entities import RegistroAuditoria


class AuditoriaMapper:
    """Conversión entre entidad de dominio RegistroAuditoria y AuditLogDTO."""

    @staticmethod
    def a_dto(entidad: RegistroAuditoria) -> AuditLogDTO:
        return AuditLogDTO(
            id=entidad.id,
            registrado_en=entidad.registrado_en,
            actor_email=entidad.actor_email,
            actor_ip=entidad.actor_ip,
            categoria=cast(CategoriaAuditType, entidad.categoria),
            accion=entidad.accion,
            resultado=cast(ResultadoAuditType, entidad.resultado),
            recurso_tipo=entidad.recurso_tipo,
            recurso_id=entidad.recurso_id,
            metadatos=entidad.metadatos,
        )

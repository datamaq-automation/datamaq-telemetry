"""src/application/use_cases/gestionar_auditoria.py — Casos de uso de auditoría."""

import uuid
from datetime import datetime, timezone

from src.application.dtos.audit_dto import (
    AuditLogDTO,
    ConsultarAuditLogsQueryDTO,
    RegistrarAuditLogDTO,
)
from src.application.mappers.auditoria_mapper import AuditoriaMapper
from src.domain.auditoria.entities import RegistroAuditoria
from src.domain.auditoria.ports import RepositorioAuditoriaPort
from src.domain.auditoria.services import SanitizadorAuditoriaService


class RegistrarEventoAuditoriaUseCase:
    """Registra de forma inmutable un evento en el log de auditoría (append-only)."""

    def __init__(self, repo_auditoria: RepositorioAuditoriaPort) -> None:
        self.repo_auditoria = repo_auditoria

    def ejecutar(self, dto: RegistrarAuditLogDTO) -> AuditLogDTO:
        metadatos_limpios = SanitizadorAuditoriaService.sanitizar_metadatos(dto.metadatos)
        ahora = datetime.now(timezone.utc)

        evento = RegistroAuditoria(
            id=str(uuid.uuid4()),
            registrado_en=ahora,
            categoria=dto.categoria,
            accion=dto.accion,
            resultado=dto.resultado,
            actor_usuario_id=dto.actor_usuario_id,
            actor_email=dto.actor_email,
            actor_ip=dto.actor_ip,
            actor_user_agent=dto.actor_user_agent,
            recurso_tipo=dto.recurso_tipo,
            recurso_id=dto.recurso_id,
            metadatos=metadatos_limpios,
        )

        guardado = self.repo_auditoria.registrar(evento)
        return AuditoriaMapper.a_dto(guardado)


class ConsultarAuditLogsUseCase:
    """Consulta los registros de auditoría filtrados y paginados."""

    def __init__(self, repo_auditoria: RepositorioAuditoriaPort) -> None:
        self.repo_auditoria = repo_auditoria

    def ejecutar(self, query: ConsultarAuditLogsQueryDTO) -> list[AuditLogDTO]:
        registros = self.repo_auditoria.listar(
            categoria=query.categoria,
            accion=query.accion,
            actor_usuario_id=query.actor_usuario_id,
            recurso_tipo=query.recurso_tipo,
            recurso_id=query.recurso_id,
            desde=query.desde,
            hasta=query.hasta,
            limite=query.limite,
            offset=query.offset,
        )
        return [AuditoriaMapper.a_dto(r) for r in registros]

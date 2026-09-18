"""src/infrastructure/sqlalchemy/repositories/auditoria_repository.py — Repositorio SQLAlchemy de auditoría inmutable."""

from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.domain.auditoria.entities import RegistroAuditoria
from src.domain.auditoria.ports import RepositorioAuditoriaPort
from src.infrastructure.sqlalchemy.models import AuditLogModel


class MySQLAuditoriaRepository(RepositorioAuditoriaPort):
    """Implementación append-only de RepositorioAuditoriaPort sobre MySQL/SQLAlchemy."""

    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: AuditLogModel) -> RegistroAuditoria:
        return RegistroAuditoria(
            id=model.id,
            registrado_en=model.registrado_en,
            categoria=model.categoria,
            accion=model.accion,
            resultado=model.resultado,
            actor_usuario_id=model.actor_usuario_id,
            actor_email=model.actor_email,
            actor_ip=model.actor_ip,
            actor_user_agent=model.actor_user_agent,
            recurso_tipo=model.recurso_tipo,
            recurso_id=model.recurso_id,
            metadatos=model.metadatos,
        )

    def registrar(self, evento: RegistroAuditoria) -> RegistroAuditoria:
        model = AuditLogModel(
            id=evento.id,
            registrado_en=evento.registrado_en,
            actor_usuario_id=evento.actor_usuario_id,
            actor_email=evento.actor_email,
            actor_ip=evento.actor_ip,
            actor_user_agent=evento.actor_user_agent,
            categoria=evento.categoria,
            accion=evento.accion,
            resultado=evento.resultado,
            recurso_tipo=evento.recurso_tipo,
            recurso_id=evento.recurso_id,
            metadatos=evento.metadatos,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def _aplicar_filtros(
        self,
        query: Any,
        categoria: str | None = None,
        accion: str | None = None,
        actor_usuario_id: str | None = None,
        recurso_tipo: str | None = None,
        recurso_id: str | None = None,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> Any:
        if categoria:
            query = query.filter(AuditLogModel.categoria == categoria)
        if accion:
            query = query.filter(AuditLogModel.accion == accion)
        if actor_usuario_id:
            query = query.filter(AuditLogModel.actor_usuario_id == actor_usuario_id)
        if recurso_tipo:
            query = query.filter(AuditLogModel.recurso_tipo == recurso_tipo)
        if recurso_id:
            query = query.filter(AuditLogModel.recurso_id == recurso_id)
        if desde:
            query = query.filter(AuditLogModel.registrado_en >= desde)
        if hasta:
            query = query.filter(AuditLogModel.registrado_en <= hasta)
        return query

    def listar(
        self,
        categoria: str | None = None,
        accion: str | None = None,
        actor_usuario_id: str | None = None,
        recurso_tipo: str | None = None,
        recurso_id: str | None = None,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        limite: int = 100,
        offset: int = 0,
    ) -> list[RegistroAuditoria]:
        q = self.db.query(AuditLogModel)
        q = self._aplicar_filtros(
            q,
            categoria=categoria,
            accion=accion,
            actor_usuario_id=actor_usuario_id,
            recurso_tipo=recurso_tipo,
            recurso_id=recurso_id,
            desde=desde,
            hasta=hasta,
        )
        models = q.order_by(AuditLogModel.registrado_en.desc()).offset(offset).limit(limite).all()
        return [self._to_entity(m) for m in models]

    def contar(
        self,
        categoria: str | None = None,
        accion: str | None = None,
        actor_usuario_id: str | None = None,
        recurso_tipo: str | None = None,
        recurso_id: str | None = None,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> int:
        q = self.db.query(func.count(AuditLogModel.id))
        q = self._aplicar_filtros(
            q,
            categoria=categoria,
            accion=accion,
            actor_usuario_id=actor_usuario_id,
            recurso_tipo=recurso_tipo,
            recurso_id=recurso_id,
            desde=desde,
            hasta=hasta,
        )
        total = q.scalar()
        return int(total or 0)

"""src/domain/auditoria/ports.py — Puertos de auditoría."""

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.auditoria.entities import RegistroAuditoria


class RepositorioAuditoriaPort(ABC):
    """Puerto para persistencia y consulta inmutable de registros de auditoría."""

    @abstractmethod
    def registrar(self, evento: RegistroAuditoria) -> RegistroAuditoria:
        """Registra un evento inmutable (append-only)."""
        ...

    @abstractmethod
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
        """Consulta eventos de auditoría ordenados cronológicamente descendente."""
        ...

    @abstractmethod
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
        """Cuenta la cantidad total de eventos que cumplen con los filtros."""
        ...

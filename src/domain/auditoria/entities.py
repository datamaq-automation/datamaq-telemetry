"""src/domain/auditoria/entities.py — Entidades del dominio de auditoría inmutable."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class RegistroAuditoria:
    """Entidad inmutable de registro de auditoría técnica (ISO 27001 A.8.15 / Ley 25.326)."""

    id: str
    registrado_en: datetime
    categoria: str
    accion: str
    resultado: str
    actor_usuario_id: str | None = None
    actor_email: str | None = None
    actor_ip: str | None = None
    actor_user_agent: str | None = None
    recurso_tipo: str | None = None
    recurso_id: str | None = None
    metadatos: dict[str, Any] | None = None

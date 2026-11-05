"""src/infrastructure/fastapi/dependencies_auditoria_ti.py."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from src.application.use_cases.consultar_auditoria_cambios_ti import ConsultarAuditoriaCambiosTIUseCase
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.repositories.auditoria_cambios_ti_repository import AuditoriaCambiosTIRepository


def get_consultar_auditoria_cambios_ti(
    db: Annotated[Session, Depends(get_db_session)],
) -> ConsultarAuditoriaCambiosTIUseCase:
    """Caso de uso de auditoría de cambios de TI con su repositorio SQLAlchemy de la sesión."""
    return ConsultarAuditoriaCambiosTIUseCase(AuditoriaCambiosTIRepository(db))

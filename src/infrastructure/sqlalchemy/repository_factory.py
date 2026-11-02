"""src/infrastructure/sqlalchemy/repository_factory.py.

Implementación concreta de RepositorioFactoryPort respaldada por SQLAlchemy.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.domain.telemetria.ports import (
    RepositorioDispositivosPort,
    RepositorioFactoryPort,
    RepositorioPlanesPort,
    RepositorioSuscripcionesPort,
    RepositorioTelemetriaPort,
)
from src.infrastructure.sqlalchemy.mysql_repositories import (
    MySQLDispositivosRepository,
    MySQLPlanesRepository,
    MySQLSuscripcionesRepository,
    MySQLTelemetriaRepository,
)


class SQLAlchemyRepositorioFactory(RepositorioFactoryPort):
    """Abstract Factory concreta para la familia de repositorios SQLAlchemy."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def dispositivos(self) -> RepositorioDispositivosPort:
        return MySQLDispositivosRepository(self._db)

    def telemetria(self) -> RepositorioTelemetriaPort:
        return MySQLTelemetriaRepository(self._db)

    def suscripciones(self) -> RepositorioSuscripcionesPort:
        return MySQLSuscripcionesRepository(self._db)

    def planes(self) -> RepositorioPlanesPort:
        return MySQLPlanesRepository(self._db)

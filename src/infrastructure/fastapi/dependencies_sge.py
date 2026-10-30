"""src/infrastructure/fastapi/dependencies_sge.py."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from src.application.use_cases.consultar_costo_estimado import ConsultarCostoEstimadoUseCase
from src.domain.telemetria.ports import RepositorioOrganizacionesPort
from src.infrastructure.fastapi.dependencies import get_db_session, get_settings_dep, get_telemetria_use_case
from src.infrastructure.settings.config import Settings
from src.infrastructure.sqlalchemy.mysql_repositories import MySQLTelemetriaRepository
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

_repositorio_organizaciones_singleton: RepositorioOrganizacionesPort = YamlOrganizacionesRepository()


def get_organizaciones_repository() -> RepositorioOrganizacionesPort:
    return _repositorio_organizaciones_singleton


def get_consultar_costo_estimado_use_case(
    db: Annotated[Session, Depends(get_db_session)],
    repo_org: Annotated[
        RepositorioOrganizacionesPort,
        Depends(get_organizaciones_repository),
    ],
    settings: Annotated[
        Settings,
        Depends(get_settings_dep),
    ],
) -> ConsultarCostoEstimadoUseCase:
    return ConsultarCostoEstimadoUseCase(
        repo_organizaciones=repo_org,
        repo_telemetria=MySQLTelemetriaRepository(db),
        consultar_telemetria=get_telemetria_use_case(db, settings),
    )

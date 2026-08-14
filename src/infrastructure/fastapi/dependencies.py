from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from src.adapters.controllers.dispositivos_controller import DispositivosController
from src.adapters.controllers.telemetria_controller import TelemetriaController
from src.adapters.gateways.in_memory_event_broadcaster import InMemoryEventBroadcaster
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.application.use_cases.gestionar_dispositivos import (
    GestionarDispositivosUseCase,
)
from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.mysql_repositories import (
    MySQLDispositivosRepository,
    MySQLOrganizacionesRepository,
    MySQLTelemetriaRepository,
)

# Singleton in-memory broadcaster
global_event_broadcaster = InMemoryEventBroadcaster()


def get_broadcaster() -> InMemoryEventBroadcaster:
    return global_event_broadcaster


def get_telemetria_controller(
    db: Annotated[Session, Depends(get_db_session)],
    broadcaster: Annotated[InMemoryEventBroadcaster, Depends(get_broadcaster)],
) -> TelemetriaController:
    repo_disp = MySQLDispositivosRepository(db)
    repo_telem = MySQLTelemetriaRepository(db)
    consultar_uc = ConsultarTelemetriaUseCase(repo_telem, repo_disp)
    ingestar_uc = IngestarTelemetriaUseCase(repo_disp, repo_telem, broadcaster)
    return TelemetriaController(consultar_uc, ingestar_uc)


def get_dispositivos_controller(
    db: Annotated[Session, Depends(get_db_session)],
) -> DispositivosController:
    repo_disp = MySQLDispositivosRepository(db)
    repo_org = MySQLOrganizacionesRepository(db)
    use_case = GestionarDispositivosUseCase(repo_disp, repo_org)
    return DispositivosController(use_case)

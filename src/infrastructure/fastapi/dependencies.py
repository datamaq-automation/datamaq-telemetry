from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from src.adapters.controllers.alertas_controller import AlertasController
from src.adapters.controllers.auth_controller import AuthController
from src.adapters.controllers.dispositivos_controller import DispositivosController
from src.adapters.controllers.planes_controller import PlanesController
from src.adapters.controllers.purga_controller import PurgaController
from src.adapters.controllers.telemetria_controller import TelemetriaController
from src.adapters.gateways.in_memory_event_broadcaster import InMemoryEventBroadcaster
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.application.use_cases.gestionar_alertas import GestionarAlertasUseCase
from src.application.use_cases.gestionar_dispositivos import (
    GestionarDispositivosUseCase,
)
from src.application.use_cases.gestionar_planes import GestionarPlanesUseCase
from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.application.use_cases.purgar_telemetria import PurgarTelemetriaExpiradaUseCase
from src.domain.auth.services import HashContrasenaService
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.settings.config import get_settings
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.mysql_repositories import (
    MySQLDispositivosRepository,
    MySQLOrganizacionesRepository,
    MySQLPlanesRepository,
    MySQLTelemetriaRepository,
    MySQLUsuariosRepository,
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
    repo_org = MySQLOrganizacionesRepository(db)
    repo_planes = MySQLPlanesRepository(db)
    logger = get_logger("telemetria_api")
    consultar_uc = ConsultarTelemetriaUseCase(repo_telem, repo_disp, repo_org, repo_planes)
    ingestar_uc = IngestarTelemetriaUseCase(repo_disp, repo_telem, broadcaster, logger=logger)
    return TelemetriaController(consultar_uc, ingestar_uc)


def get_dispositivos_controller(
    db: Annotated[Session, Depends(get_db_session)],
) -> DispositivosController:
    repo_disp = MySQLDispositivosRepository(db)
    repo_org = MySQLOrganizacionesRepository(db)
    repo_planes = MySQLPlanesRepository(db)
    use_case = GestionarDispositivosUseCase(repo_disp, repo_org, repo_planes)
    return DispositivosController(use_case)


def get_planes_controller(
    db: Annotated[Session, Depends(get_db_session)],
) -> PlanesController:
    repo_planes = MySQLPlanesRepository(db)
    use_case = GestionarPlanesUseCase(repo_planes)
    return PlanesController(use_case)


def get_purga_controller(
    db: Annotated[Session, Depends(get_db_session)],
) -> PurgaController:
    repo_telem = MySQLTelemetriaRepository(db)
    logger = get_logger("purga_telemetria")
    use_case = PurgarTelemetriaExpiradaUseCase(repo_telem, logger=logger)
    return PurgaController(use_case)


def get_alertas_controller(
    db: Annotated[Session, Depends(get_db_session)],
) -> AlertasController:
    repo_telem = MySQLTelemetriaRepository(db)
    use_case = GestionarAlertasUseCase(repo_telem)
    return AlertasController(use_case)


def get_auth_controller(
    db: Annotated[Session, Depends(get_db_session)],
) -> AuthController:
    repo_usuarios = MySQLUsuariosRepository(db)
    settings = get_settings()
    use_case = AutenticarUsuarioUseCase(
        repo_usuarios=repo_usuarios,
        hash_service=HashContrasenaService(),
        token_service=JwtTokenService(settings.API_SECRET_KEY),
        minutos_validez=settings.AUTH_TOKEN_EXPIRA_MINUTOS,
    )
    return AuthController(use_case)


def get_usuario_actual(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    settings = get_settings()
    token_service = JwtTokenService(settings.API_SECRET_KEY)
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="credenciales_invalidas")
    token = authorization.removeprefix("Bearer ").strip()
    claims = token_service.verificar(token)
    if claims is None:
        raise HTTPException(status_code=401, detail="credenciales_invalidas")
    return claims

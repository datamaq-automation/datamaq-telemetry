from functools import lru_cache
from typing import Annotated, Any

from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from src.adapters.controllers.unifilar_topologia_controller import UnifilarTopologiaController
from src.adapters.gateways.in_memory_event_broadcaster import InMemoryEventBroadcaster
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.application.use_cases.consultar_unifilar_topologia import ConsultarUnifilarTopologiaUseCase
from src.application.use_cases.gestionar_alertas import GestionarAlertasUseCase
from src.application.use_cases.gestionar_dispositivos import (
    GestionarDispositivosUseCase,
)
from src.application.use_cases.gestionar_planes import GestionarPlanesUseCase
from src.application.use_cases.gestionar_planta_estructura import (
    GestionarPlantaEstructuraUseCase,
)
from src.application.use_cases.purgar_telemetria import PurgarTelemetriaExpiradaUseCase
from src.domain.auth.services import HashContrasenaService, RateLimiterService
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.paho_mqtt.mqtt_listener import MQTTListener
from src.infrastructure.settings.config import Settings, get_settings
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

# Listener MQTT registrado en el lifespan del servidor (estado de conexión)
_mqtt_listener_registrado: MQTTListener | None = None


def registrar_mqtt_listener(listener: MQTTListener) -> None:
    """Registra el listener MQTT activo para que /health consulte su estado."""
    global _mqtt_listener_registrado
    _mqtt_listener_registrado = listener


def get_mqtt_listener() -> MQTTListener | None:
    """Devuelve el listener MQTT registrado, o None si aún no se ha iniciado."""
    return _mqtt_listener_registrado


def get_broadcaster() -> InMemoryEventBroadcaster:
    return global_event_broadcaster


def get_settings_dep() -> Settings:
    """Dependencia FastAPI que inyecta la configuración de la aplicación."""
    return get_settings()


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiterService:
    settings = get_settings()
    return RateLimiterService(
        max_intentos=settings.LOGIN_MAX_INTENTOS,
        ventana_segundos=settings.LOGIN_VENTANA_SEGUNDOS,
    )


def get_telemetria_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> ConsultarTelemetriaUseCase:
    repo_disp = MySQLDispositivosRepository(db)
    repo_telem = MySQLTelemetriaRepository(db)
    repo_org = MySQLOrganizacionesRepository(db)
    repo_planes = MySQLPlanesRepository(db)
    return ConsultarTelemetriaUseCase(repo_telem, repo_disp, repo_org, repo_planes)


def get_dispositivos_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> GestionarDispositivosUseCase:
    repo_disp = MySQLDispositivosRepository(db)
    repo_org = MySQLOrganizacionesRepository(db)
    repo_planes = MySQLPlanesRepository(db)
    return GestionarDispositivosUseCase(repo_disp, repo_org, repo_planes)


def get_planes_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> GestionarPlanesUseCase:
    repo_planes = MySQLPlanesRepository(db)
    return GestionarPlanesUseCase(repo_planes)


def get_purga_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> PurgarTelemetriaExpiradaUseCase:
    repo_telem = MySQLTelemetriaRepository(db)
    logger = get_logger("purga_telemetria")
    return PurgarTelemetriaExpiradaUseCase(repo_telem, logger=logger)


def get_alertas_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> GestionarAlertasUseCase:
    repo_telem = MySQLTelemetriaRepository(db)
    repo_disp = MySQLDispositivosRepository(db)
    return GestionarAlertasUseCase(
        repo_telemetria=repo_telem,
        publicador=global_event_broadcaster,
        repo_dispositivos=repo_disp,
    )


def get_planta_estructura_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> GestionarPlantaEstructuraUseCase:
    repo_org = MySQLOrganizacionesRepository(db)
    return GestionarPlantaEstructuraUseCase(repo_org)


def get_unifilar_topologia_controller(
    db: Annotated[Session, Depends(get_db_session)],
) -> UnifilarTopologiaController:
    repo_org = MySQLOrganizacionesRepository(db)
    use_case = ConsultarUnifilarTopologiaUseCase(repo_org)
    return UnifilarTopologiaController(use_case)


def get_auth_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> AutenticarUsuarioUseCase:
    repo_usuarios = MySQLUsuariosRepository(db)
    settings = get_settings()
    rate_limiter = get_rate_limiter()
    return AutenticarUsuarioUseCase(
        repo_usuarios=repo_usuarios,
        hash_service=HashContrasenaService(),
        token_service=JwtTokenService(settings.API_SECRET_KEY),
        minutos_validez=settings.AUTH_TOKEN_EXPIRA_MINUTOS,
        rate_limiter=rate_limiter,
    )


def extraer_token(cookie_valor: str | None, authorization: str | None) -> str | None:
    """Extrae el token desde la cookie HttpOnly o del header Bearer; None si no hay credenciales."""
    if cookie_valor:
        return cookie_valor
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return None


def token_valido(
    cookie_valor: str | None,
    authorization: str | None,
    secreto: str,
    secreto_anterior: str = "",
) -> bool:
    """Valida un token JWT desde cookie o header Bearer."""
    token = extraer_token(cookie_valor, authorization)
    if token is None:
        return False
    adicionales = [secreto_anterior] if secreto_anterior else None
    return JwtTokenService(secreto).verificar(token, adicionales) is not None


def get_usuario_actual(
    authorization: Annotated[str | None, Header()] = None,
    datamaq_token: Annotated[str | None, Cookie()] = None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.AUTH_REQUIRED:
        return {"sub": "anon", "rol": "admin"}
    token = extraer_token(datamaq_token, authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="credenciales_invalidas")
    token_service = JwtTokenService(settings.API_SECRET_KEY)
    adicionales = [settings.API_SECRET_KEY_ANTERIOR] if settings.API_SECRET_KEY_ANTERIOR else None
    claims = token_service.verificar(token, adicionales)
    if claims is None:
        raise HTTPException(status_code=401, detail="credenciales_invalidas")
    return claims


def requiere_rol_admin(claims: Annotated[dict[str, Any], Depends(get_usuario_actual)]) -> dict[str, Any]:
    if claims.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    return claims


def requiere_rol_escritura(claims: Annotated[dict[str, Any], Depends(get_usuario_actual)]) -> dict[str, Any]:
    if claims.get("rol") == "invitado":
        raise HTTPException(status_code=403, detail="forbidden")
    return claims

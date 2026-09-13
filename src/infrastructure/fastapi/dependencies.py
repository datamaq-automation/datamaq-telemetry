"""src/infrastructure/fastapi/dependencies.py."""

from functools import lru_cache
from typing import Annotated, Any

from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from src.adapters.gateways.in_memory_event_broadcaster import InMemoryEventBroadcaster
from src.adapters.gateways.in_memory_telemetria_buffer import InMemoryTelemetriaBuffer
from src.adapters.gateways.mqtt_comando_rafaga import MqttComandoRafagaGateway
from src.application.use_cases.analizar_consumo import AnalizarConsumoUseCase
from src.application.use_cases.asistente.procesar_pregunta_asistente import (
    ProcesarPreguntaAsistenteUseCase,
)
from src.application.use_cases.atribuir_consumo import AtribuirConsumoUseCase
from src.application.use_cases.caracterizar_carga import CaracterizarCargaUseCase
from src.application.use_cases.consultar_grupo_dispositivos import ConsultarGrupoDispositivosUseCase
from src.application.use_cases.consultar_nodo_unifilar import ConsultarNodoUnifilarUseCase
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.application.use_cases.exportar_cargas import ExportarCargasUseCase
from src.application.use_cases.exportar_disponibilidad import ExportarDisponibilidadUseCase
from src.application.use_cases.exportar_telemetria import ExportarTelemetriaUseCase
from src.application.use_cases.gestionar_alertas import GestionarAlertasUseCase
from src.application.use_cases.gestionar_cargas import GestionarCargasUseCase
from src.application.use_cases.gestionar_disponibilidad import GestionarDisponibilidadUseCase
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.application.use_cases.gestionar_grupos_dispositivos import GestionarGruposDispositivosUseCase
from src.application.use_cases.gestionar_maquinas import GestionarMaquinasUseCase
from src.application.use_cases.gestionar_planes import GestionarPlanesUseCase
from src.application.use_cases.gestionar_planta_estructura import GestionarPlantaEstructuraUseCase
from src.application.use_cases.ingesta.registro_campanas import registro_campanas_activas
from src.application.use_cases.purgar_telemetria import PurgarTelemetriaExpiradaUseCase
from src.application.use_cases.recuperar_contrasena import (
    RestablecerContrasenaUseCase,
    SolicitarRecuperacionContrasenaUseCase,
)
from src.domain.auth.ports import (
    GeneradorTokenPort,
    RepositorioUsuariosPort,
    ServicioEmailPort,
)
from src.domain.auth.services import HashContrasenaService, RateLimiterService, TokenRevocationService
from src.infrastructure.auth.email_service import SmtpEmailService
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.paho_mqtt.mqtt_listener import MQTTListener
from src.infrastructure.settings.config import Settings, get_settings
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.mysql_repositories import (
    MySQLCampanasRepository,
    MySQLCargasRepository,
    MySQLDispositivosRepository,
    MySQLEventosDisponibilidadRepository,
    MySQLGruposDispositivosRepository,
    MySQLIntervalosActividadRepository,
    MySQLMaquinasRepository,
    MySQLParadasProgramadasRepository,
    MySQLPlanesRepository,
    MySQLSeriePotenciaRepository,
    MySQLTelemetriaRepository,
    MySQLUsuariosRepository,
)
from src.infrastructure.yaml.repositories.organizaciones_repository import (
    YamlOrganizacionesRepository,
)

# Singleton in-memory broadcaster
global_event_broadcaster = InMemoryEventBroadcaster()

# Singleton en RAM de últimas lecturas en vivo por dispositivo (sobrevive a un F5 del navegador)
global_telemetria_buffer = InMemoryTelemetriaBuffer()

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


def get_telemetria_buffer() -> InMemoryTelemetriaBuffer:
    return global_telemetria_buffer


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
    repo_org = YamlOrganizacionesRepository()
    repo_planes = MySQLPlanesRepository(db)
    return ConsultarTelemetriaUseCase(
        repo_telem, repo_disp, repo_org, repo_planes, buffer_en_vivo=global_telemetria_buffer
    )


def get_exportar_telemetria_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> ExportarTelemetriaUseCase:
    return ExportarTelemetriaUseCase(
        repo_telemetria=MySQLTelemetriaRepository(db),
        repo_dispositivos=MySQLDispositivosRepository(db),
    )


def get_exportar_disponibilidad_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> ExportarDisponibilidadUseCase:
    return ExportarDisponibilidadUseCase(
        repo_maquinas=MySQLMaquinasRepository(db),
        repo_eventos=MySQLEventosDisponibilidadRepository(db),
    )


def get_exportar_cargas_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> ExportarCargasUseCase:
    return ExportarCargasUseCase(
        repo_cargas=MySQLCargasRepository(db),
        repo_intervalos=MySQLIntervalosActividadRepository(db),
    )


def get_dispositivos_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> GestionarDispositivosUseCase:
    return GestionarDispositivosUseCase(
        MySQLDispositivosRepository(db),
        YamlOrganizacionesRepository(),
        MySQLPlanesRepository(db),
    )


def get_grupos_dispositivos_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> GestionarGruposDispositivosUseCase:
    return GestionarGruposDispositivosUseCase(
        MySQLGruposDispositivosRepository(db),
        MySQLDispositivosRepository(db),
    )


def get_consultar_grupo_dispositivos_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> ConsultarGrupoDispositivosUseCase:
    return ConsultarGrupoDispositivosUseCase(
        MySQLGruposDispositivosRepository(db),
        MySQLTelemetriaRepository(db),
        get_telemetria_use_case(db),
    )


def get_planes_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> GestionarPlanesUseCase:
    return GestionarPlanesUseCase(MySQLPlanesRepository(db))


def get_purga_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> PurgarTelemetriaExpiradaUseCase:
    repo_telem = MySQLTelemetriaRepository(db)
    logger = get_logger("purga_telemetria")
    return PurgarTelemetriaExpiradaUseCase(repo_telem, logger=logger)


def get_alertas_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> GestionarAlertasUseCase:
    return GestionarAlertasUseCase(
        repo_telemetria=MySQLTelemetriaRepository(db),
        publicador=global_event_broadcaster,
        repo_dispositivos=MySQLDispositivosRepository(db),
    )


def get_procesar_pregunta_asistente_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> ProcesarPreguntaAsistenteUseCase:
    from src.infrastructure.asistente.clasificador_reglas import (
        ClasificadorIntencionReglasAdapter,
    )
    from src.infrastructure.groq.groq_adapter import GroqRespuestaAdapter
    from src.infrastructure.sqlalchemy.repositories.asistente_repository import (
        MySQLConversacionesAsistenteRepository,
    )

    return ProcesarPreguntaAsistenteUseCase(
        clasificador=ClasificadorIntencionReglasAdapter(),
        generador=GroqRespuestaAdapter(),
        repo_conversaciones=MySQLConversacionesAsistenteRepository(db),
        gestor_alertas=get_alertas_use_case(db),
        gestor_dispositivos=get_dispositivos_use_case(db),
    )


def get_consultar_analitica_planta_use_case() -> Any:
    from src.application.use_cases.consultar_analitica_planta import (
        ConsultarAnaliticaPlantaUseCase,
    )

    return ConsultarAnaliticaPlantaUseCase()


def get_procesar_chat_copilot_use_case() -> Any:
    from src.application.use_cases.copilot.procesar_chat_copilot import (
        ProcesarChatCopilotUseCase,
    )

    return ProcesarChatCopilotUseCase()


def get_maquinas_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> GestionarMaquinasUseCase:
    return GestionarMaquinasUseCase(
        MySQLMaquinasRepository(db),
        MySQLTelemetriaRepository(db),
        MySQLDispositivosRepository(db),
        YamlOrganizacionesRepository(),
    )


def get_cargas_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> GestionarCargasUseCase:
    return GestionarCargasUseCase(MySQLCargasRepository(db))


def get_caracterizacion_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> CaracterizarCargaUseCase:
    return CaracterizarCargaUseCase(
        repo_campanas=MySQLCampanasRepository(db),
        repo_cargas=MySQLCargasRepository(db),
        repo_dispositivos=MySQLDispositivosRepository(db),
        registro=registro_campanas_activas,
        comando_rafaga=MqttComandoRafagaGateway(get_mqtt_listener()),
    )


def get_atribucion_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> AtribuirConsumoUseCase:
    return AtribuirConsumoUseCase(
        repo_serie=MySQLSeriePotenciaRepository(db),
        repo_cargas=MySQLCargasRepository(db),
        repo_intervalos=MySQLIntervalosActividadRepository(db),
    )


def get_analisis_consumo_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> AnalizarConsumoUseCase:
    return AnalizarConsumoUseCase(MySQLSeriePotenciaRepository(db))


def get_disponibilidad_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> GestionarDisponibilidadUseCase:
    return GestionarDisponibilidadUseCase(
        MySQLMaquinasRepository(db),
        MySQLEventosDisponibilidadRepository(db),
        MySQLParadasProgramadasRepository(db),
        MySQLDispositivosRepository(db),
        YamlOrganizacionesRepository(),
    )


def get_planta_estructura_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> GestionarPlantaEstructuraUseCase:
    repo_org = YamlOrganizacionesRepository()
    return GestionarPlantaEstructuraUseCase(repo_org)


def get_consultar_nodo_unifilar_use_case(
    db: Annotated[Session, Depends(get_db_session)],
) -> ConsultarNodoUnifilarUseCase:
    return ConsultarNodoUnifilarUseCase(
        YamlOrganizacionesRepository(),
        MySQLTelemetriaRepository(db),
        get_telemetria_use_case(db),
    )


def get_usuarios_repository(
    db: Annotated[Session, Depends(get_db_session)],
) -> RepositorioUsuariosPort:
    return MySQLUsuariosRepository(db)


@lru_cache(maxsize=1)
def get_email_service_singleton(
    host: str,
    port: int,
    user: str,
    password: str,
    use_tls: bool,
    from_email: str,
    app_env: str,
) -> SmtpEmailService:
    return SmtpEmailService(
        host=host,
        port=port,
        user=user,
        password=password,
        use_tls=use_tls,
        from_email=from_email,
        app_env=app_env,
    )


def get_email_service(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ServicioEmailPort:
    return get_email_service_singleton(
        settings.SMTP_HOST,
        settings.SMTP_PORT,
        settings.SMTP_USER,
        settings.SMTP_PASSWORD,
        settings.SMTP_TLS,
        settings.SMTP_FROM,
        settings.APP_ENV,
    )


def get_token_service(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> GeneradorTokenPort:
    return JwtTokenService(settings.API_SECRET_KEY)


@lru_cache(maxsize=1)
def get_token_revocation_service() -> TokenRevocationService:
    return TokenRevocationService()


def get_solicitar_recuperacion_use_case(
    usuarios_repo: Annotated[RepositorioUsuariosPort, Depends(get_usuarios_repository)],
    token_service: Annotated[GeneradorTokenPort, Depends(get_token_service)],
    email_service: Annotated[ServicioEmailPort, Depends(get_email_service)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> SolicitarRecuperacionContrasenaUseCase:
    return SolicitarRecuperacionContrasenaUseCase(
        repositorio_usuarios=usuarios_repo,
        generador_token=token_service,
        servicio_email=email_service,
        frontend_url=settings.FRONTEND_URL,
        minutos_expiracion=settings.RECUPERACION_TOKEN_EXPIRA_MINUTOS,
        rate_limiter=get_rate_limiter(),
    )


def get_restablecer_contrasena_use_case(
    usuarios_repo: Annotated[RepositorioUsuariosPort, Depends(get_usuarios_repository)],
    token_service: Annotated[GeneradorTokenPort, Depends(get_token_service)],
) -> RestablecerContrasenaUseCase:
    return RestablecerContrasenaUseCase(
        repositorio_usuarios=usuarios_repo,
        generador_token=token_service,
        hash_service=HashContrasenaService(),
        revocation_service=get_token_revocation_service(),
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

    # Verificación de revocación de sesión por cambio de contraseña o logout
    revocation = get_token_revocation_service()
    if revocation.esta_revocado(str(claims.get("sub", "")), int(claims.get("iat", 0))):
        raise HTTPException(status_code=401, detail="credenciales_invalidas")

    return claims


def requiere_rol_superadmin(claims: Annotated[dict[str, Any], Depends(get_usuario_actual)]) -> dict[str, Any]:
    if claims.get("rol") != "superadmin":
        raise HTTPException(status_code=403, detail="forbidden")
    return claims


def requiere_rol_admin(claims: Annotated[dict[str, Any], Depends(get_usuario_actual)]) -> dict[str, Any]:
    if claims.get("rol") not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="forbidden")
    return claims


def requiere_rol_escritura(claims: Annotated[dict[str, Any], Depends(get_usuario_actual)]) -> dict[str, Any]:
    if claims.get("rol") in ("invitado", "invitado_global"):
        raise HTTPException(status_code=403, detail="forbidden")
    return claims


def no_permitido_para_invitados_2fa(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
) -> dict[str, Any]:
    """Rechaza con 403 intentos de configuración, activación o desactivación de 2FA
    por parte de usuarios con roles efímeros o no persistentes (invitado e invitado_global).
    """
    if claims.get("rol") in ("invitado", "invitado_global"):
        raise HTTPException(status_code=403, detail="2fa_no_disponible_para_invitado")
    return claims

"""src/infrastructure/fastapi/routes/auth_router.py."""

from datetime import datetime, timezone
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Cookie, Depends, Request, Response

from src.application.dtos.audit_dto import RegistrarAuditLogDTO
from src.application.dtos.auth_dto import (
    Activar2FARequestDTO,
    Desactivar2FARequestDTO,
    LoginRequestDTO,
    LoginResponseDTO,
    MeResponseDTO,
    Operacion2FAResponseDTO,
    RestablecerContrasenaDTO,
    RevocarDispositivosResponseDTO,
    Setup2FAResponseDTO,
    SolicitarRecuperacionDTO,
    Verificar2FARequestDTO,
)
from src.application.dtos.cambio_contrasena_dto import (
    ConfirmPasswordChangeRequest,
    ConfirmPasswordChangeResponse,
    RequestPasswordChangeCodeRequest,
    RequestPasswordChangeCodeResponse,
)
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.application.use_cases.cambio_contrasena import (
    ConfirmarCambioContrasenaUseCase,
    SolicitarCambioContrasenaUseCase,
)
from src.application.use_cases.gestionar_2fa import (
    Activar2FAUseCase,
    Desactivar2FAUseCase,
    Setup2FAUseCase,
    Verificar2FAUseCase,
)
from src.application.use_cases.gestionar_auditoria import RegistrarEventoAuditoriaUseCase
from src.application.use_cases.gestionar_dispositivos_confiables import (
    RevocarDispositivosConfiablesUseCase,
)
from src.application.use_cases.recuperar_contrasena import (
    RestablecerContrasenaUseCase,
    SolicitarRecuperacionContrasenaUseCase,
)
from src.domain.auth.ports import RepositorioUsuariosPort
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi.auth_cookies import (
    DEVICE_TRUST_COOKIE,
    _eliminar_cookie,
    _fijar_cookie,
    _fijar_cookie_dispositivo,
)
from src.infrastructure.fastapi.auth_cookies import (
    DEVICE_TRUST_MAX_AGE as DEVICE_TRUST_MAX_AGE,
)
from src.infrastructure.fastapi.auth_dependencies import (
    get_activar_2fa_use_case,
    get_auth_use_case,
    get_desactivar_2fa_use_case,
    get_revocar_dispositivos_use_case,
    get_setup_2fa_use_case,
    get_verificar_2fa_use_case,
)
from src.infrastructure.fastapi.dependencies import (
    get_registrar_auditoria_use_case,
    get_restablecer_contrasena_use_case,
    get_settings_dep,
    get_solicitar_recuperacion_use_case,
    get_token_revocation_service,
    get_usuario_actual,
    get_usuarios_repository,
    no_permitido_para_invitados_2fa,
)
from src.infrastructure.fastapi.dependencies_cambio_contrasena import (
    get_confirmar_cambio_contrasena_use_case,
    get_solicitar_cambio_contrasena_use_case,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http
from src.infrastructure.settings.config import Settings

router = APIRouter(prefix="/api/v1/auth", tags=["Autenticación"])

logger = structlog.get_logger("auth")


def _obtener_ip_cliente(request: Request | None) -> str:
    if request is None:
        return "desconocida"
    return request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (
        request.client.host if request.client else "desconocida"
    )


@router.post("/login", response_model=LoginResponseDTO)
def login(
    dto: LoginRequestDTO,
    use_case: Annotated[AutenticarUsuarioUseCase, Depends(get_auth_use_case)],
    response: Response,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    request: Request = None,  # type: ignore[assignment]
    datamaq_device_trust: Annotated[str | None, Cookie()] = None,
    audit_use_case: Annotated[RegistrarEventoAuditoriaUseCase | None, Depends(get_registrar_auditoria_use_case)] = None,
):
    ip = _obtener_ip_cliente(request)
    user_agent = request.headers.get("User-Agent", "") if request is not None else ""
    try:
        resultado = use_case.login(
            dto,
            clave_ip=ip,
            device_token=datamaq_device_trust,
            ip_origen=ip,
        )
        logger.info(
            "login_exitoso",
            usuario=dto.usuario,
            request_id=structlog.contextvars.get_contextvars().get("request_id"),
        )
        if resultado.token:
            _fijar_cookie(response, settings, resultado.token, request=request)

        if audit_use_case is not None:
            try:
                token_claims = (
                    JwtTokenService(settings.API_SECRET_KEY).verificar(resultado.token) if resultado.token else None
                )
                user_id = token_claims.get("sub") if token_claims else None
                audit_use_case.ejecutar(
                    RegistrarAuditLogDTO(
                        categoria="AUTH",
                        accion="LOGIN_EXITOSO",
                        resultado="EXITO",
                        actor_usuario_id=user_id,
                        actor_email=dto.usuario,
                        actor_ip=ip,
                        actor_user_agent=user_agent,
                        recurso_tipo="usuario",
                        recurso_id=user_id,
                        metadatos={"requiere_2fa": resultado.require_2fa},
                    )
                )
            except Exception as err:
                logger.warning("error_registrando_auditoria_login", error=str(err))

        return resultado
    except Exception as e:
        if audit_use_case is not None:
            try:
                audit_use_case.ejecutar(
                    RegistrarAuditLogDTO(
                        categoria="AUTH",
                        accion="LOGIN_FALLIDO",
                        resultado="RECHAZADO",
                        actor_email=dto.usuario,
                        actor_ip=ip,
                        actor_user_agent=user_agent,
                        recurso_tipo="usuario",
                        metadatos={"motivo": type(e).__name__},
                    )
                )
            except Exception as err:
                logger.warning("error_registrando_auditoria_login_fallido", error=str(err))
        manejar_error_http(e)


@router.post("/logout")
def logout(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    request: Request = None,  # type: ignore[assignment]
    audit_use_case: Annotated[RegistrarEventoAuditoriaUseCase | None, Depends(get_registrar_auditoria_use_case)] = None,
) -> dict[str, str]:
    _eliminar_cookie(response, settings, request=request)
    if audit_use_case is not None and request is not None:
        try:
            ip = _obtener_ip_cliente(request)
            user_agent = request.headers.get("User-Agent", "")
            token = request.cookies.get(settings.AUTH_COOKIE_NOMBRE) or request.headers.get(
                "Authorization", ""
            ).replace("Bearer ", "")
            usuario_id = None
            if token:
                c = JwtTokenService(settings.API_SECRET_KEY).verificar(token)
                if c:
                    usuario_id = str(c.get("sub", ""))
            audit_use_case.ejecutar(
                RegistrarAuditLogDTO(
                    categoria="AUTH",
                    accion="LOGOUT",
                    resultado="EXITO",
                    actor_usuario_id=usuario_id,
                    actor_ip=ip,
                    actor_user_agent=user_agent,
                    recurso_tipo="usuario",
                    recurso_id=usuario_id,
                )
            )
        except Exception as err:
            logger.warning("error_registrando_auditoria_logout", error=str(err))
    return {"detail": "sesion_cerrada"}


@router.post("/logout-todas")
def logout_todas(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    response: Response,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    repo_usuarios: Annotated[RepositorioUsuariosPort, Depends(get_usuarios_repository)],
    audit_use_case: Annotated[RegistrarEventoAuditoriaUseCase | None, Depends(get_registrar_auditoria_use_case)] = None,
    request: Request = None,  # type: ignore[assignment]
) -> dict[str, str]:
    usuario_id = str(claims.get("sub", ""))
    ahora = datetime.now(timezone.utc)

    usuario = repo_usuarios.obtener_por_id(usuario_id)
    if usuario is not None:
        usuario.sesiones_revocadas_antes_de = ahora
        repo_usuarios.guardar(usuario)

    # Invalida también en memoria
    revocation = get_token_revocation_service()
    revocation.revocar_usuario(usuario_id, int(ahora.timestamp()))

    # Limpia la cookie del cliente invocador
    _eliminar_cookie(response, settings, request=request)

    # Registra evento inmutable en audit_logs (ISO 27001 A.5.15 & A.8.15)
    if audit_use_case is not None:
        try:
            ip = _obtener_ip_cliente(request)
            user_agent = request.headers.get("User-Agent", "") if request is not None else ""
            audit_use_case.ejecutar(
                RegistrarAuditLogDTO(
                    categoria="AUTH",
                    accion="LOGOUT_TODAS_SESIONES",
                    resultado="EXITO",
                    actor_usuario_id=usuario_id,
                    actor_email=str(claims.get("usuario") or ""),
                    actor_ip=ip,
                    actor_user_agent=user_agent,
                    recurso_tipo="usuario",
                    recurso_id=usuario_id,
                    metadatos={"sesiones_revocadas_antes_de": ahora.isoformat()},
                )
            )
        except Exception as err:
            logger.warning("error_registrando_auditoria_logout_todas", error=str(err))

    return {"detail": "todas_las_sesiones_revocadas"}


@router.get("/me", response_model=MeResponseDTO)
def me(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    use_case: Annotated[AutenticarUsuarioUseCase, Depends(get_auth_use_case)],
) -> MeResponseDTO:
    try:
        return use_case.me(claims)
    except Exception as e:
        manejar_error_http(e)


@router.post("/2fa/verificar", response_model=LoginResponseDTO)
def verificar_2fa(
    dto: Verificar2FARequestDTO,
    use_case: Annotated[Verificar2FAUseCase, Depends(get_verificar_2fa_use_case)],
    response: Response,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    request: Request = None,  # type: ignore[assignment]
    audit_use_case: Annotated[RegistrarEventoAuditoriaUseCase | None, Depends(get_registrar_auditoria_use_case)] = None,
) -> LoginResponseDTO:
    ip = _obtener_ip_cliente(request)
    user_agent = request.headers.get("User-Agent", "") if request is not None else ""
    try:
        resultado = use_case.verificar(dto, ip_origen=ip, user_agent=user_agent)
        if resultado.token:
            _fijar_cookie(response, settings, resultado.token, request=request)
        if resultado.device_trust_token:
            _fijar_cookie_dispositivo(response, settings, resultado.device_trust_token, request=request)

        if audit_use_case is not None:
            try:
                token_claims = (
                    JwtTokenService(settings.API_SECRET_KEY).verificar(resultado.token) if resultado.token else None
                )
                user_id = token_claims.get("sub") if token_claims else None
                user_email = token_claims.get("usuario") if token_claims else None
                audit_use_case.ejecutar(
                    RegistrarAuditLogDTO(
                        categoria="AUTH",
                        accion="LOGIN_EXITOSO",
                        resultado="EXITO",
                        actor_usuario_id=user_id,
                        actor_email=user_email,
                        actor_ip=ip,
                        actor_user_agent=user_agent,
                        recurso_tipo="usuario",
                        recurso_id=user_id,
                        metadatos={"mfa": True},
                    )
                )
            except Exception as err:
                logger.warning("error_registrando_auditoria_2fa_exitoso", error=str(err))

        return resultado
    except Exception as e:
        if audit_use_case is not None:
            try:
                audit_use_case.ejecutar(
                    RegistrarAuditLogDTO(
                        categoria="AUTH",
                        accion="LOGIN_FALLIDO",
                        resultado="RECHAZADO",
                        actor_ip=ip,
                        actor_user_agent=user_agent,
                        recurso_tipo="usuario",
                        metadatos={"mfa": True, "motivo": type(e).__name__},
                    )
                )
            except Exception as err:
                logger.warning("error_registrando_auditoria_2fa_fallido", error=str(err))
        manejar_error_http(e)


@router.post(
    "/2fa/setup",
    response_model=Setup2FAResponseDTO,
    dependencies=[Depends(no_permitido_para_invitados_2fa)],
)
def setup_2fa(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    use_case: Annotated[Setup2FAUseCase, Depends(get_setup_2fa_use_case)],
) -> Setup2FAResponseDTO:
    try:
        usuario = str(claims.get("usuario") or claims.get("sub"))
        return use_case.ejecutar(usuario)
    except Exception as e:
        manejar_error_http(e)


@router.post(
    "/2fa/activar",
    response_model=Operacion2FAResponseDTO,
    dependencies=[Depends(no_permitido_para_invitados_2fa)],
)
def activar_2fa(
    dto: Activar2FARequestDTO,
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    use_case: Annotated[Activar2FAUseCase, Depends(get_activar_2fa_use_case)],
    audit_use_case: Annotated[RegistrarEventoAuditoriaUseCase | None, Depends(get_registrar_auditoria_use_case)] = None,
    request: Request = None,  # type: ignore[assignment]
) -> Operacion2FAResponseDTO:
    try:
        usuario = str(claims.get("usuario") or claims.get("sub"))
        usuario_id = str(claims.get("sub", ""))
        resultado = use_case.ejecutar(usuario, dto)

        if audit_use_case is not None:
            try:
                ip = _obtener_ip_cliente(request)
                user_agent = request.headers.get("User-Agent", "") if request is not None else ""
                audit_use_case.ejecutar(
                    RegistrarAuditLogDTO(
                        categoria="AUTH",
                        accion="2FA_ACTIVADO",
                        resultado="EXITO",
                        actor_usuario_id=usuario_id,
                        actor_email=str(claims.get("usuario") or ""),
                        actor_ip=ip,
                        actor_user_agent=user_agent,
                        recurso_tipo="usuario",
                        recurso_id=usuario_id,
                    )
                )
            except Exception as err:
                logger.warning("error_registrando_auditoria_2fa_activado", error=str(err))

        return resultado
    except Exception as e:
        manejar_error_http(e)


@router.post(
    "/2fa/desactivar",
    response_model=Operacion2FAResponseDTO,
    dependencies=[Depends(no_permitido_para_invitados_2fa)],
)
def desactivar_2fa(
    dto: Desactivar2FARequestDTO,
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    use_case: Annotated[Desactivar2FAUseCase, Depends(get_desactivar_2fa_use_case)],
    audit_use_case: Annotated[RegistrarEventoAuditoriaUseCase | None, Depends(get_registrar_auditoria_use_case)] = None,
    request: Request = None,  # type: ignore[assignment]
) -> Operacion2FAResponseDTO:
    try:
        usuario = str(claims.get("usuario") or claims.get("sub"))
        usuario_id = str(claims.get("sub", ""))
        resultado = use_case.ejecutar(usuario, dto)

        if audit_use_case is not None:
            try:
                ip = _obtener_ip_cliente(request)
                user_agent = request.headers.get("User-Agent", "") if request is not None else ""
                audit_use_case.ejecutar(
                    RegistrarAuditLogDTO(
                        categoria="AUTH",
                        accion="2FA_DESACTIVADO",
                        resultado="EXITO",
                        actor_usuario_id=usuario_id,
                        actor_email=str(claims.get("usuario") or ""),
                        actor_ip=ip,
                        actor_user_agent=user_agent,
                        recurso_tipo="usuario",
                        recurso_id=usuario_id,
                    )
                )
            except Exception as err:
                logger.warning("error_registrando_auditoria_2fa_desactivado", error=str(err))

        return resultado
    except Exception as e:
        manejar_error_http(e)


@router.post("/recuperar-contrasena", response_model=Operacion2FAResponseDTO)
def solicitar_recuperacion(
    dto: SolicitarRecuperacionDTO,
    use_case: Annotated[
        SolicitarRecuperacionContrasenaUseCase,
        Depends(get_solicitar_recuperacion_use_case),
    ],
    request: Request = None,  # type: ignore[assignment]
) -> Operacion2FAResponseDTO:
    try:
        ip = "desconocida"
        if request is not None:
            ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (
                request.client.host if request.client else "desconocida"
            )
        return use_case.ejecutar(dto, clave_ip=ip)
    except Exception as e:
        manejar_error_http(e)


@router.post("/restablecer-contrasena", response_model=Operacion2FAResponseDTO)
def restablecer_contrasena(
    dto: RestablecerContrasenaDTO,
    use_case: Annotated[
        RestablecerContrasenaUseCase,
        Depends(get_restablecer_contrasena_use_case),
    ],
) -> Operacion2FAResponseDTO:
    try:
        return use_case.ejecutar(dto)
    except Exception as e:
        manejar_error_http(e)


@router.post("/dispositivos/revocar-todos", response_model=RevocarDispositivosResponseDTO)
def revocar_dispositivos(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    use_case: Annotated[RevocarDispositivosConfiablesUseCase, Depends(get_revocar_dispositivos_use_case)],
    response: Response,
) -> RevocarDispositivosResponseDTO:
    try:
        usuario_id = str(claims.get("sub"))
        cantidad = use_case.ejecutar(usuario_id)
        response.delete_cookie(key=DEVICE_TRUST_COOKIE, path="/api/v1/auth")
        return RevocarDispositivosResponseDTO(cantidad_revocados=cantidad)
    except Exception as e:
        manejar_error_http(e)


@router.patch("/request-password-change-code", response_model=RequestPasswordChangeCodeResponse)
def request_password_change_code(
    dto: RequestPasswordChangeCodeRequest,
    request: Request,
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    use_case: Annotated[SolicitarCambioContrasenaUseCase, Depends(get_solicitar_cambio_contrasena_use_case)],
) -> RequestPasswordChangeCodeResponse:
    """Valida la contraseña actual y envía un código OTP de 4 dígitos al email del usuario."""
    try:
        resultado = use_case.ejecutar(
            usuario_id=str(claims.get("sub")),
            password_actual=dto.password_actual,
            ip=_obtener_ip_cliente(request),
            user_agent=request.headers.get("User-Agent"),
        )
        return RequestPasswordChangeCodeResponse(email_destino=resultado.email_destino)
    except Exception as e:
        manejar_error_http(e)


@router.patch("/confirm-password-change", response_model=ConfirmPasswordChangeResponse)
def confirm_password_change(
    dto: ConfirmPasswordChangeRequest,
    request: Request,
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    use_case: Annotated[ConfirmarCambioContrasenaUseCase, Depends(get_confirmar_cambio_contrasena_use_case)],
) -> ConfirmPasswordChangeResponse:
    """Valida el código OTP, cambia la contraseña y cierra todas las sesiones del usuario."""
    try:
        use_case.ejecutar(
            usuario_id=str(claims.get("sub")),
            codigo=dto.codigo,
            password_nueva=dto.password_nueva,
            ip=_obtener_ip_cliente(request),
            user_agent=request.headers.get("User-Agent"),
        )
        return ConfirmPasswordChangeResponse(
            status="cambio_exitoso",
            mensaje="Contraseña actualizada. Por favor vuelva a iniciar sesión.",
        )
    except Exception as e:
        manejar_error_http(e)

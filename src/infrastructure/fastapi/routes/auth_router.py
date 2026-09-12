"""src/infrastructure/fastapi/routes/auth_router.py."""
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Cookie, Depends, Request, Response

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
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.application.use_cases.gestionar_2fa import (
    Activar2FAUseCase,
    Desactivar2FAUseCase,
    Setup2FAUseCase,
    Verificar2FAUseCase,
)
from src.application.use_cases.gestionar_dispositivos_confiables import (
    RevocarDispositivosConfiablesUseCase,
)
from src.application.use_cases.recuperar_contrasena import (
    RestablecerContrasenaUseCase,
    SolicitarRecuperacionContrasenaUseCase,
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
    get_restablecer_contrasena_use_case,
    get_settings_dep,
    get_solicitar_recuperacion_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http
from src.infrastructure.settings.config import Settings

router = APIRouter(prefix="/api/v1/auth", tags=["Autenticación"])

logger = structlog.get_logger("auth")

DEVICE_TRUST_COOKIE = "datamaq_device_trust"
DEVICE_TRUST_MAX_AGE = 60 * 60 * 24 * 30  # 30 días


def _fijar_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.AUTH_COOKIE_NOMBRE,
        value=token,
        max_age=settings.auth_cookie_max_age,
        httponly=settings.AUTH_COOKIE_HTTPONLY,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        secure=settings.auth_cookie_secure,
    )


def _fijar_cookie_dispositivo(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=DEVICE_TRUST_COOKIE,
        value=token,
        max_age=DEVICE_TRUST_MAX_AGE,
        httponly=True,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        secure=settings.auth_cookie_secure,
        path="/api/v1/auth",
    )


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
):
    try:
        ip = _obtener_ip_cliente(request)
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
            _fijar_cookie(response, settings, resultado.token)
        return resultado
    except Exception as e:
        manejar_error_http(e)


@router.post("/guest", response_model=LoginResponseDTO)
def guest(
    request: Request,
    response: Response,
    use_case: Annotated[AutenticarUsuarioUseCase, Depends(get_auth_use_case)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> LoginResponseDTO:
    try:
        ip = request.client.host if request.client else "desconocida"
        resultado = use_case.guest(clave_limite=f"ip:{ip}")
        logger.info(
            "login_exitoso",
            usuario="invitado",
            request_id=structlog.contextvars.get_contextvars().get("request_id"),
        )
        if resultado.token:
            _fijar_cookie(response, settings, resultado.token)
        return resultado
    except Exception as e:
        manejar_error_http(e)


@router.post("/logout")
def logout(response: Response, settings: Annotated[Settings, Depends(get_settings_dep)]) -> dict[str, str]:
    response.delete_cookie(key=settings.AUTH_COOKIE_NOMBRE)
    return {"detail": "sesion_cerrada"}


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
) -> LoginResponseDTO:
    try:
        ip = _obtener_ip_cliente(request)
        user_agent = request.headers.get("User-Agent", "") if request is not None else ""
        resultado = use_case.verificar(dto, ip_origen=ip, user_agent=user_agent)
        if resultado.token:
            _fijar_cookie(response, settings, resultado.token)
        if resultado.device_trust_token:
            _fijar_cookie_dispositivo(response, settings, resultado.device_trust_token)
        return resultado
    except Exception as e:
        manejar_error_http(e)


@router.post("/2fa/setup", response_model=Setup2FAResponseDTO)
def setup_2fa(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    use_case: Annotated[Setup2FAUseCase, Depends(get_setup_2fa_use_case)],
) -> Setup2FAResponseDTO:
    try:
        usuario = str(claims.get("usuario") or claims.get("sub"))
        return use_case.ejecutar(usuario)
    except Exception as e:
        manejar_error_http(e)


@router.post("/2fa/activar", response_model=Operacion2FAResponseDTO)
def activar_2fa(
    dto: Activar2FARequestDTO,
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    use_case: Annotated[Activar2FAUseCase, Depends(get_activar_2fa_use_case)],
) -> Operacion2FAResponseDTO:
    try:
        usuario = str(claims.get("usuario") or claims.get("sub"))
        return use_case.ejecutar(usuario, dto)
    except Exception as e:
        manejar_error_http(e)


@router.post("/2fa/desactivar", response_model=Operacion2FAResponseDTO)
def desactivar_2fa(
    dto: Desactivar2FARequestDTO,
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    use_case: Annotated[Desactivar2FAUseCase, Depends(get_desactivar_2fa_use_case)],
) -> Operacion2FAResponseDTO:
    try:
        usuario = str(claims.get("usuario") or claims.get("sub"))
        return use_case.ejecutar(usuario, dto)
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

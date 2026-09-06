from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Request, Response

from src.application.dtos.auth_dto import (
    Activar2FARequestDTO,
    Desactivar2FARequestDTO,
    LoginRequestDTO,
    LoginResponseDTO,
    MeResponseDTO,
    Operacion2FAResponseDTO,
    Setup2FAResponseDTO,
    Verificar2FARequestDTO,
)
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.application.use_cases.gestionar_2fa import (
    Activar2FAUseCase,
    Desactivar2FAUseCase,
    Setup2FAUseCase,
    Verificar2FAUseCase,
)
from src.infrastructure.fastapi.dependencies import (
    get_activar_2fa_use_case,
    get_auth_use_case,
    get_desactivar_2fa_use_case,
    get_settings_dep,
    get_setup_2fa_use_case,
    get_usuario_actual,
    get_verificar_2fa_use_case,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http
from src.infrastructure.settings.config import Settings

router = APIRouter(prefix="/api/v1/auth", tags=["Autenticación"])

logger = structlog.get_logger("auth")


def _fijar_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.AUTH_COOKIE_NOMBRE,
        value=token,
        max_age=settings.auth_cookie_max_age,
        httponly=settings.AUTH_COOKIE_HTTPONLY,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        secure=settings.auth_cookie_secure,
    )


@router.post("/login", response_model=LoginResponseDTO)
def login(
    dto: LoginRequestDTO,
    use_case: Annotated[AutenticarUsuarioUseCase, Depends(get_auth_use_case)],
    response: Response,
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    try:
        resultado = use_case.login(dto)
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
) -> LoginResponseDTO:
    try:
        resultado = use_case.verificar(dto)
        if resultado.token:
            _fijar_cookie(response, settings, resultado.token)
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

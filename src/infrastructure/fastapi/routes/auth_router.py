from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Request, Response

from src.adapters.controllers.auth_controller import AuthController
from src.application.dtos.auth_dto import LoginRequestDTO, LoginResponseDTO, MeResponseDTO
from src.infrastructure.fastapi.dependencies import get_auth_controller, get_settings_dep, get_usuario_actual
from src.infrastructure.fastapi.error_handler import manejar_error_http
from src.infrastructure.settings.config import Settings

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])

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
    controller: Annotated[AuthController, Depends(get_auth_controller)],
    response: Response,
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    try:
        resultado = controller.login(dto)
        logger.info(
            "login_exitoso",
            usuario=dto.usuario,
            request_id=structlog.contextvars.get_contextvars().get("request_id"),
        )
        _fijar_cookie(response, settings, resultado.token)
        return resultado
    except Exception as e:
        manejar_error_http(e)


@router.post("/guest", response_model=LoginResponseDTO)
def guest(
    request: Request,
    response: Response,
    controller: Annotated[AuthController, Depends(get_auth_controller)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> LoginResponseDTO:
    try:
        ip = request.client.host if request.client else "desconocida"
        resultado = controller.guest(clave_limite=f"ip:{ip}")
        logger.info(
            "login_exitoso",
            usuario="invitado",
            request_id=structlog.contextvars.get_contextvars().get("request_id"),
        )
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
    controller: Annotated[AuthController, Depends(get_auth_controller)],
) -> MeResponseDTO:
    try:
        return controller.me(claims)
    except Exception as e:
        manejar_error_http(e)

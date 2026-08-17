from typing import Annotated

from fastapi import APIRouter, Depends, Response

from src.adapters.controllers.auth_controller import AuthController
from src.application.dtos.auth_dto import LoginRequestDTO, LoginResponseDTO
from src.infrastructure.fastapi.dependencies import get_auth_controller, get_settings_dep
from src.infrastructure.fastapi.error_handler import manejar_error_http
from src.infrastructure.settings.config import Settings

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])


@router.post("/login", response_model=LoginResponseDTO)
def login(
    dto: LoginRequestDTO,
    controller: Annotated[AuthController, Depends(get_auth_controller)],
    response: Response,
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    try:
        resultado = controller.login(dto)
        response.set_cookie(
            key=settings.AUTH_COOKIE_NOMBRE,
            value=resultado.token,
            max_age=settings.auth_cookie_max_age,
            httponly=settings.AUTH_COOKIE_HTTPONLY,
            samesite=settings.AUTH_COOKIE_SAMESITE,
            secure=settings.auth_cookie_secure,
        )
        return resultado
    except Exception as e:
        manejar_error_http(e)


@router.post("/logout")
def logout(response: Response, settings: Annotated[Settings, Depends(get_settings_dep)]) -> dict[str, str]:
    response.delete_cookie(key=settings.AUTH_COOKIE_NOMBRE)
    return {"detail": "sesion_cerrada"}

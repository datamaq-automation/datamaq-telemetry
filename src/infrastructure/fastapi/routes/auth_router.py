from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from src.adapters.controllers.auth_controller import AuthController
from src.adapters.presenters.error_presenter import ErrorPresenter
from src.application.dtos.auth_dto import LoginRequestDTO, LoginResponseDTO
from src.infrastructure.fastapi.dependencies import get_auth_controller
from src.infrastructure.settings.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])


@router.post("/login", response_model=LoginResponseDTO)
def login(
    dto: LoginRequestDTO,
    controller: Annotated[AuthController, Depends(get_auth_controller)],
    response: Response,
):
    try:
        resultado = controller.login(dto)
        settings = get_settings()
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
        code, err = ErrorPresenter.presentar_excepcion(e)
        raise HTTPException(status_code=code, detail=err["mensaje"]) from e


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    settings = get_settings()
    response.delete_cookie(key=settings.AUTH_COOKIE_NOMBRE)
    return {"detail": "sesion_cerrada"}

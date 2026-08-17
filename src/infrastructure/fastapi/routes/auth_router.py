from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.adapters.controllers.auth_controller import AuthController
from src.adapters.presenters.error_presenter import ErrorPresenter
from src.application.dtos.auth_dto import LoginRequestDTO, LoginResponseDTO
from src.infrastructure.fastapi.dependencies import get_auth_controller

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])


@router.post("/login", response_model=LoginResponseDTO)
def login(
    dto: LoginRequestDTO,
    controller: Annotated[AuthController, Depends(get_auth_controller)],
):
    try:
        return controller.login(dto)
    except Exception as e:
        code, err = ErrorPresenter.presentar_excepcion(e)
        raise HTTPException(status_code=code, detail=err["mensaje"]) from e

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.adapters.controllers.purga_controller import PurgaController
from src.adapters.presenters.error_presenter import ErrorPresenter
from src.application.dtos.purga_dto import PurgaRequestDTO, PurgaResultadoDTO
from src.infrastructure.fastapi.dependencies import get_purga_controller

router = APIRouter(tags=["Sistema"])


@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/api/system/purge", response_model=PurgaResultadoDTO)
def trigger_purge(
    controller: Annotated[PurgaController, Depends(get_purga_controller)],
    dto: PurgaRequestDTO | None = None,
):
    try:
        req = dto or PurgaRequestDTO()
        return controller.ejecutar_purga(req)
    except Exception as e:
        code, err = ErrorPresenter.presentar_excepcion(e)
        raise HTTPException(status_code=code, detail=err["mensaje"]) from e

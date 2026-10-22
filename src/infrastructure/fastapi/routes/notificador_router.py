"""src/infrastructure/fastapi/routes/notificador_router.py."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.dtos.notificador_dto import NotificadorEstadoDTO
from src.application.use_cases.monitorear_potencia_y_alarma import MonitorearPotenciaYAlarmaUseCase
from src.infrastructure.fastapi.dependencies import (
    get_monitorear_potencia_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.planta_ownership import resolver_planta_permitida
from src.infrastructure.settings.logger import get_logger

router = APIRouter(prefix="/api/v1", tags=["Notificador"])
logger = get_logger("notificador")
_ERROR_INTERNO = "Ocurrió un error interno en el servidor"


@router.get(
    "/tuya/notificador/estado",
    response_model=NotificadorEstadoDTO,
    dependencies=[Depends(resolver_planta_permitida)],
    status_code=status.HTTP_200_OK,
)
async def estado_alarma(
    planta_id: str = Query(..., description="ID de la planta industrial"),
    user_claims: Annotated[dict[str, Any] | None, Depends(get_usuario_actual)] = None,
    use_case: Annotated[
        MonitorearPotenciaYAlarmaUseCase | None,
        Depends(get_monitorear_potencia_use_case),
    ] = None,
) -> NotificadorEstadoDTO:
    """Retorna el estado actual de la alarma de potencia.

    Requiere que el usuario sea propietario de la planta.
    """
    if use_case is None:
        logger.error("notificador_use_case_no_inyectado", planta_id=planta_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_ERROR_INTERNO)

    try:
        return await use_case.ejecutar(planta_id)
    except Exception as e:
        logger.error("notificador_error_evaluando_alarma", exc_info=True, planta_id=planta_id, error=str(e))
        raise HTTPException(status_code=500, detail=_ERROR_INTERNO) from e

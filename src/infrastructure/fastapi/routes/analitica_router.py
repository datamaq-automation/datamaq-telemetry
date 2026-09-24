# src/infrastructure/fastapi/routes/analitica_router.py
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.dtos.analitica_dto import (
    AnaliticaBancoCapacitoresPlantaDTO,
    AnaliticaPenalizacionesPlantaDTO,
)
from src.application.use_cases.consultar_analitica_planta import (
    ConsultarAnaliticaPlantaUseCase,
)
from src.infrastructure.fastapi.dependencies import (
    get_consultar_analitica_planta_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.planta_ownership import resolver_planta_permitida

router = APIRouter(prefix="/api/v1/analitica", tags=["Analítica SSOT de Planta"])


@router.get(
    "/banco-capacitores/planta",
    dependencies=[Depends(resolver_planta_permitida)],
    response_model=AnaliticaBancoCapacitoresPlantaDTO,
    status_code=status.HTTP_200_OK,
    summary="Obtener analítica SSOT de banco de capacitores (histórico real 30 días)",
)
def obtener_banco_capacitores_planta(
    planta_id: str = Query(..., description="ID de la planta industrial"),
    periodo_dias: int = Query(default=30, description="Ventana de análisis en días (rango 7-60, ISO 50001: mínimo 30)"),
    user_claims: Annotated[dict[str, Any] | None, Depends(get_usuario_actual)] = None,
    use_case: Annotated[
        ConsultarAnaliticaPlantaUseCase | None, Depends(get_consultar_analitica_planta_use_case)
    ] = None,
) -> AnaliticaBancoCapacitoresPlantaDTO:
    if use_case is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Use case no inyectado")

    try:
        return use_case.obtener_banco_capacitores(planta_id=planta_id, periodo_dias=periodo_dias)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo analítica de banco de capacitores: {err}",
        ) from err


@router.get(
    "/penalizaciones/planta",
    dependencies=[Depends(resolver_planta_permitida)],
    response_model=AnaliticaPenalizacionesPlantaDTO,
    status_code=status.HTTP_200_OK,
    summary="Obtener acumulado SSOT de penalizaciones por bajo FP a 7 días",
)
def obtener_penalizaciones_planta(
    planta_id: str = Query(..., description="ID de la planta industrial"),
    user_claims: Annotated[dict[str, Any] | None, Depends(get_usuario_actual)] = None,
    use_case: Annotated[
        ConsultarAnaliticaPlantaUseCase | None, Depends(get_consultar_analitica_planta_use_case)
    ] = None,
) -> AnaliticaPenalizacionesPlantaDTO:
    if use_case is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Use case no inyectado")

    try:
        return use_case.obtener_penalizaciones(planta_id=planta_id)

    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo analítica de penalizaciones: {err}",
        ) from err

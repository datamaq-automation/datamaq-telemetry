"""src/infrastructure/fastapi/routes/maquinas_router.py."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.application.dtos.maquina_dto import ListaMaquinasInferidaDTO
from src.application.use_cases.consultar_maquinas_inferidas import ConsultarMaquinasInferidaUseCase
from src.infrastructure.fastapi.dependencies import (
    get_consultar_maquinas_inferidas_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_dispositivo

router = APIRouter(
    prefix="/api/v1/dispositivos",
    tags=["Máquinas Inferidas"],
    dependencies=[Depends(get_usuario_actual), Depends(verificar_propiedad_dispositivo)],
)


@router.get(
    "/{dispositivo_id}/maquinas/inferidas",
    response_model=ListaMaquinasInferidaDTO,
)
def obtener_maquinas_inferidas(
    dispositivo_id: str,
    use_case: Annotated[ConsultarMaquinasInferidaUseCase, Depends(get_consultar_maquinas_inferidas_use_case)],
) -> ListaMaquinasInferidaDTO:
    """Obtiene máquinas propuestas por energy-ml para un dispositivo.

    Máquinas inferidas son candidatas de cargas detectadas automáticamente por el
    modelo de ML (energy-ml) que corren cada 3:30 AM UTC. Cada máquina tiene:
    - id: UUID único
    - nombre: propuesto por ML
    - tipo_maquina: categoría (motor, compresor, etc.)
    - confianza: score de confianza [0.0, 1.0]
    - patrones_detectados: lista de patrones observados
    - energia_kwh_mes: consumo estimado del período
    - costo_estimado_ars: costo estimado en ARS

    Requiere:
    - Token de autenticación válido
    - Acceso a la planta del dispositivo

    Args:
        dispositivo_id: ID del dispositivo

    Returns:
        ListaMaquinasInferidaDTO con máquinas inferidas ordenadas por confianza DESC
    """
    # planta_permitida valida acceso automáticamente (resolver_planta_permitida)
    # Si llega aquí, el acceso está permitido
    return use_case(dispositivo_id)

# src/infrastructure/fastapi/routes/copilot_router.py
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.dtos.copilot_dto import (
    CopilotChatRequestDTO,
    CopilotChatResponseDTO,
)
from src.application.use_cases.copilot.procesar_chat_copilot import (
    ProcesarChatCopilotUseCase,
)
from src.infrastructure.fastapi.dependencies import (
    get_procesar_chat_copilot_use_case,
    get_usuario_actual,
)

router = APIRouter(prefix="/api/v1/copilot", tags=["Co-Pilot Conversacional"])


@router.post(
    "/chat",
    response_model=CopilotChatResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Interacción conversacional con el Co-Pilot metrológico",
)
def chat(
    dto: CopilotChatRequestDTO,
    user_claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    use_case: Annotated[ProcesarChatCopilotUseCase, Depends(get_procesar_chat_copilot_use_case)],
) -> CopilotChatResponseDTO:
    try:
        organizacion_id = str(user_claims.get("organizacion_id") or "")
        user_id = str(user_claims.get("user_id") or user_claims.get("sub") or "")
        return use_case.ejecutar(
            dto=dto,
            organizacion_id=organizacion_id,
            usuario_id=user_id,
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error procesando la consulta de Co-Pilot: {err}",
        ) from err

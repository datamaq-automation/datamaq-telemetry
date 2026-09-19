# src/infrastructure/fastapi/routes/asistente_router.py
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.application.use_cases.asistente.procesar_pregunta_asistente import (
    ProcesarPreguntaAsistenteUseCase,
)
from src.infrastructure.fastapi.dependencies import (
    get_procesar_pregunta_asistente_use_case,
    get_usuario_actual,
)

router = APIRouter(prefix="/api/v1/asistente", tags=["Asistente Conversacional"])


class PreguntaRequestDTO(BaseModel):
    pregunta: str = Field(..., min_length=2, description="Pregunta en lenguaje natural sobre telemetría o alertas")
    conversacion_id: str | None = Field(default=None, description="ID opcional de conversación previa")


class PreguntaResponseDTO(BaseModel):
    respuesta: str
    intencion_detectada: str | None


@router.post(
    "/preguntar",
    response_model=PreguntaResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar al Asistente Conversacional sobre el estado operativo de la planta",
)
def preguntar(
    dto: PreguntaRequestDTO,
    user_claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    use_case: Annotated[ProcesarPreguntaAsistenteUseCase, Depends(get_procesar_pregunta_asistente_use_case)],
) -> PreguntaResponseDTO:
    try:
        organizacion_id = str(user_claims.get("organizacion_id") or "")
        user_id = str(user_claims.get("user_id") or user_claims.get("sub") or "")
        resultado = use_case.ejecutar(
            pregunta=dto.pregunta,
            organizacion_id=organizacion_id,
            usuario_id=user_id,
            conversacion_id=dto.conversacion_id,
        )
        return PreguntaResponseDTO(
            respuesta=resultado.texto,
            intencion_detectada=resultado.intencion,
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error procesando la consulta del asistente: {err}",
        ) from err

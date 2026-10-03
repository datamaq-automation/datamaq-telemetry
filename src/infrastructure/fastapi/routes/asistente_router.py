# src/infrastructure/fastapi/routes/asistente_router.py
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.dtos.asistente_dto import (
    PreguntaRequestDTO,
    PreguntaResponseDTO,
)
from src.application.use_cases.asistente.procesar_pregunta_asistente import (
    ProcesarPreguntaAsistenteUseCase,
)
from src.infrastructure.fastapi.dependencies import (
    get_procesar_pregunta_asistente_use_case,
    get_usuario_actual,
)

router = APIRouter(prefix="/api/v1/asistente", tags=["Asistente Conversacional"])


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
    organizacion_id = str(user_claims.get("org") or "")
    if not organizacion_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="asistente_no_disponible")
    try:
        user_id = str(user_claims.get("sub") or "")
        resultado = use_case.ejecutar(
            pregunta=dto.pregunta,
            organizacion_id=organizacion_id,
            usuario_id=user_id,
            conversacion_id=dto.conversacion_id,
            usuario_consiente_envio_groq=dto.usuario_consiente_envio_groq,
        )
        return PreguntaResponseDTO(
            respuesta=resultado.texto,
            intencion_detectada=resultado.intencion,
            consentimiento_requerido=resultado.consentimiento_requerido,
            enviado_a_groq=resultado.enviado_a_groq,
            razon_sin_groq=resultado.razon_sin_groq,
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error procesando la consulta del asistente: {err}",
        ) from err

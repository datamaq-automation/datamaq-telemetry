# src/application/dtos/copilot_dto.py
from datetime import datetime

from pydantic import BaseModel, Field


class CopilotMensajeHistorialDTO(BaseModel):
    rol: str = Field(..., description="Rol del mensaje: 'usuario' o 'asistente'")
    texto: str = Field(..., description="Contenido textual del mensaje")


class CopilotChatRequestDTO(BaseModel):
    mensaje: str = Field(..., min_length=1, description="Consulta del usuario en lenguaje natural")
    dispositivo_id: str = Field(..., min_length=1, description="Identificador único del dispositivo/medidor")
    historial_contexto: list[CopilotMensajeHistorialDTO] = Field(
        default_factory=list,
        description="Historial previo de mensajes conversacionales",
    )


class CopilotDiagnosticoAdjuntoDTO(BaseModel):
    requiere_accion: bool = Field(default=False, description="Indica si se requiere acción correctiva")
    sugerencia_kvar: float | None = Field(default=None, description="Sugerencia de potencia reactiva en kVAr")
    alerta_relacionada_id: int | None = Field(default=None, description="ID de la alerta asociada si aplica")


class CopilotChatResponseDTO(BaseModel):
    mensaje_id: str = Field(..., description="ID único del mensaje de respuesta")
    respuesta: str = Field(..., description="Explicación diagnóstica generada")
    diagnostico_adjunto: CopilotDiagnosticoAdjuntoDTO | None = Field(
        default=None,
        description="Metadatos estructurados del diagnóstico",
    )
    timestamp: datetime = Field(..., description="Timestamp ISO-8601 de la respuesta")

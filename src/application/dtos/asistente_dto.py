"""src/application/dtos/asistente_dto.py — DTOs para el asistente conversacional."""

from pydantic import BaseModel, Field


class PreguntaRequestDTO(BaseModel):
    """Request para hacer una pregunta al asistente conversacional."""

    pregunta: str = Field(..., min_length=2, description="Pregunta en lenguaje natural sobre telemetría o alertas")
    conversacion_id: str | None = Field(default=None, description="ID opcional de conversación previa")
    usuario_consiente_envio_groq: bool = Field(
        default=False,
        description="Consentimiento explícito del usuario para enviar datos a Groq. Si False, respuesta local solo.",
    )


class PreguntaResponseDTO(BaseModel):
    """Response del asistente conversacional con información de auditoría."""

    respuesta: str = Field(..., description="Texto de respuesta en lenguaje natural")
    intencion_detectada: str | None = Field(default=None, description="Intención clasificada de la pregunta")
    consentimiento_requerido: bool = Field(
        default=False,
        description="True si se requería consentimiento para Groq pero no fue otorgado",
    )
    enviado_a_groq: bool = Field(default=False, description="True si la respuesta fue generada por Groq")
    razon_sin_groq: str | None = Field(
        default=None,
        description="Razón por la que NO se envió a Groq (ej: 'sin_consentimiento', 'error_groq_fallback')",
    )

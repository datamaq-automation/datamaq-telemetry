"""src/domain/asistente/entities.py."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ConsultaAsistente:
    """Pregunta de un usuario autenticado al asistente conversacional.

    `organizacion_id` es obligatorio y se resuelve siempre desde la sesión autenticada
    (nunca desde el texto de la pregunta) — es el límite de aislamiento multi-tenant.
    """

    pregunta: str
    organizacion_id: str


@dataclass(frozen=True)
class IntencionClasificada:
    """Resultado de clasificar la intención de una `ConsultaAsistente`."""

    nombre: str
    confianza: float


@dataclass(frozen=True)
class RespuestaAsistente:
    """Respuesta en lenguaje natural generada para una `ConsultaAsistente`."""

    texto: str
    intencion: str | None

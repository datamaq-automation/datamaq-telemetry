"""src/domain/asistente/entities.py."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


RolMensajeAsistente = Literal["usuario", "asistente"]


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
    consentimiento_requerido: bool = False
    enviado_a_groq: bool = False
    razon_sin_groq: str | None = None


@dataclass
class ConversacionAsistente:
    """Hilo de conversación entre un usuario y el asistente, acotado a una organización."""

    id: str
    organizacion_id: str
    usuario_id: str
    creado_en: datetime = field(default_factory=ahora_utc)
    actualizado_en: datetime = field(default_factory=ahora_utc)


@dataclass
class MensajeAsistente:
    """Un mensaje individual (de usuario o del asistente) dentro de una `ConversacionAsistente`."""

    id: str
    conversacion_id: str
    rol: RolMensajeAsistente
    texto: str
    creado_en: datetime = field(default_factory=ahora_utc)


@dataclass
class RegistroClasificacionIntencion:
    """Historial de qué intención se clasificó para un mensaje de usuario, y con qué confianza.

    Se persiste por separado del mensaje para poder auditar/mejorar el clasificador sin
    acoplar su historial al de la conversación en sí.
    """

    id: str
    mensaje_id: str
    intencion: IntencionClasificada
    clasificado_en: datetime = field(default_factory=ahora_utc)

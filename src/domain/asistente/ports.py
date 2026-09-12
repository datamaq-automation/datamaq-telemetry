"""src/domain/asistente/ports.py."""
from abc import ABC, abstractmethod
from collections.abc import Iterator

from src.domain.asistente.entities import (
    ConversacionAsistente,
    IntencionClasificada,
    MensajeAsistente,
    RegistroClasificacionIntencion,
)


class ClasificadorIntencionPort(ABC):
    """Puerto para clasificar la intención de una pregunta del usuario.

    La implementación concreta (embeddings locales, reglas, etc.) es un detalle de
    infraestructura — el dominio y la aplicación solo conocen este contrato.
    """

    @abstractmethod
    def clasificar(self, pregunta: str) -> IntencionClasificada:
        """Determina la intención más probable detrás de `pregunta` y su confianza (0-1)."""
        ...


class GeneradorRespuestaPort(ABC):
    """Puerto para generar la explicación en lenguaje natural a partir de contexto ya armado.

    `contexto` debe llegar ya resuelto y filtrado por organización (datos reales, no texto
    libre del usuario) — este puerto solo redacta, nunca decide qué datos consultar.
    """

    @abstractmethod
    def generar(self, pregunta: str, contexto: str) -> Iterator[str]:
        """Genera la respuesta en fragmentos de texto (streaming) a partir de `contexto`."""
        ...


class RepositorioConversacionesAsistentePort(ABC):
    """Puerto para persistir el historial de conversaciones, mensajes y clasificaciones.

    Toda consulta de lectura debe recibir `organizacion_id` y filtrar por él — es la misma
    responsabilidad de aislamiento multi-tenant que ya aplican el resto de los repositorios
    del proyecto (ver `src/infrastructure/sqlalchemy/repositories/`).
    """

    @abstractmethod
    def crear_conversacion(self, organizacion_id: str, usuario_id: str) -> ConversacionAsistente:
        """Crea una nueva conversación para el usuario dentro de su organización."""
        ...

    @abstractmethod
    def obtener_conversacion(self, conversacion_id: str, organizacion_id: str) -> ConversacionAsistente | None:
        """Obtiene una conversación por id, solo si pertenece a `organizacion_id`."""
        ...

    @abstractmethod
    def listar_mensajes(self, conversacion_id: str, organizacion_id: str) -> list[MensajeAsistente]:
        """Lista los mensajes de una conversación, en orden cronológico."""
        ...

    @abstractmethod
    def guardar_mensaje(self, mensaje: MensajeAsistente, organizacion_id: str) -> None:
        """Persiste un mensaje de una conversación que pertenece a `organizacion_id`."""
        ...

    @abstractmethod
    def guardar_clasificacion(self, registro: RegistroClasificacionIntencion, organizacion_id: str) -> None:
        """Persiste el resultado de clasificar la intención de un mensaje."""
        ...

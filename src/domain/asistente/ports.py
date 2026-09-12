"""src/domain/asistente/ports.py."""
from abc import ABC, abstractmethod
from collections.abc import Iterator

from src.domain.asistente.entities import IntencionClasificada


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

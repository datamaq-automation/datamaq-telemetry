"""src/domain/notificaciones/ports.py."""

from abc import ABC, abstractmethod


class PublicadorAlarmaPort(ABC):
    """Puerto para publicar comandos de alarma."""

    @abstractmethod
    async def publicar_alarma_sonora(self, activar: bool) -> bool:
        """Publica comando de activación/desactivación de alarma.

        Args:
            activar: True para activar alarma, False para desactivar.

        Returns:
            True si la publicación fue exitosa, False en caso contrario.
        """

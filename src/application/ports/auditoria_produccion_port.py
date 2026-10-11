"""src/application/ports/auditoria_produccion_port.py — Puerto de lectura de producción para auditorías.

Solo expone consultas NOMBRADAS (allowlist en el adaptador) y lecturas de entorno no secretas.
Nunca recibe SQL ni texto libre desde la capa de aplicación.
"""

from abc import ABC, abstractmethod


class AuditoriaProduccionPort(ABC):
    @abstractmethod
    def consultar(self, nombre: str) -> list[dict[str, object]]:
        """Ejecuta la consulta nombrada `nombre` en solo lectura y devuelve sus filas."""

    @abstractmethod
    def entorno_remoto(self) -> dict[str, object]:
        """Valores de entorno no secretos del despliegue remoto (nunca valores de claves)."""

    @abstractmethod
    def ejecutar_comando(self, nombre: str) -> str:
        """Ejecuta el comando remoto `nombre` de la allowlist de solo lectura y devuelve su salida."""

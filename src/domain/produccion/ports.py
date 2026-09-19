"""src/domain/produccion/ports.py — Puertos para persistencia de sensórica de proceso y configuraciones."""

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.produccion.entities import ConfiguracionMedicionMaquina
from src.domain.produccion.value_objects import LecturaVariableProceso


class RepositorioVariablesProcesoPort(ABC):
    """Puerto para persistir y consultar variables de proceso industrial."""

    @abstractmethod
    def guardar_lectura(self, lectura: LecturaVariableProceso, maquina_id: str) -> None:
        """Persiste una lectura individual de variable de proceso."""
        ...

    @abstractmethod
    def obtener_lecturas(self, maquina_id: str, desde: datetime, hasta: datetime) -> list[LecturaVariableProceso]:
        """Retorna lecturas de proceso en un intervalo temporal para una máquina."""
        ...

    @abstractmethod
    def guardar_configuracion(self, config: ConfiguracionMedicionMaquina) -> None:
        """Registra o actualiza la configuración de medición de una máquina."""
        ...

    @abstractmethod
    def obtener_configuracion(self, maquina_id: str) -> ConfiguracionMedicionMaquina | None:
        """Retorna la configuración de medición de una máquina puntual."""
        ...

"""src/adapters/gateways/in_memory_variables_proceso_repository.py."""

from datetime import datetime

from src.domain.produccion.entities import ConfiguracionMedicionMaquina
from src.domain.produccion.ports import RepositorioVariablesProcesoPort
from src.domain.produccion.value_objects import LecturaVariableProceso


class InMemoryVariablesProcesoRepository(RepositorioVariablesProcesoPort):
    """Repositorio en memoria para pruebas y desarrollo de sensórica de proceso."""

    def __init__(self) -> None:
        self._lecturas: dict[str, list[LecturaVariableProceso]] = {}
        self._configs: dict[str, ConfiguracionMedicionMaquina] = {}

    def guardar_lectura(self, lectura: LecturaVariableProceso, maquina_id: str) -> None:
        if maquina_id not in self._lecturas:
            self._lecturas[maquina_id] = []
        self._lecturas[maquina_id].append(lectura)

    def obtener_lecturas(self, maquina_id: str, desde: datetime, hasta: datetime) -> list[LecturaVariableProceso]:
        lista = self._lecturas.get(maquina_id, [])
        return [lec for lec in lista if desde <= lec.momento <= hasta]

    def guardar_configuracion(self, config: ConfiguracionMedicionMaquina) -> None:
        self._configs[config.maquina_id] = config

    def obtener_configuracion(self, maquina_id: str) -> ConfiguracionMedicionMaquina | None:
        return self._configs.get(maquina_id)

"""src/infrastructure/fastapi/dependencies_memoria.py — Repositorios en memoria de producción y SGE para la inyección de dependencias."""

from src.adapters.gateways.in_memory_documentacion_sge_repository import InMemoryDocumentacionSgeRepository
from src.adapters.gateways.in_memory_registro_capacitaciones_sge_repository import (
    InMemoryRegistroCapacitacionesSgeRepository,
)
from src.adapters.gateways.in_memory_variables_proceso_repository import InMemoryVariablesProcesoRepository
from src.domain.produccion.ports import RepositorioVariablesProcesoPort
from src.domain.sge.ports import RepositorioDocumentacionSgePort, RepositorioRegistroCapacitacionesSgePort
from src.domain.telemetria.ports import RepositorioOrganizacionesPort
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

_repo_proceso_singleton: RepositorioVariablesProcesoPort = InMemoryVariablesProcesoRepository()
_repositorio_sge_singleton: RepositorioDocumentacionSgePort = InMemoryDocumentacionSgeRepository()
_repositorio_capacitaciones_singleton: RepositorioRegistroCapacitacionesSgePort = (
    InMemoryRegistroCapacitacionesSgeRepository()
)
_repositorio_organizaciones_singleton: RepositorioOrganizacionesPort = YamlOrganizacionesRepository()


def get_variables_proceso_repository() -> RepositorioVariablesProcesoPort:
    return _repo_proceso_singleton


def get_documentacion_sge_repository() -> RepositorioDocumentacionSgePort:
    return _repositorio_sge_singleton


def get_registro_capacitaciones_repository() -> RepositorioRegistroCapacitacionesSgePort:
    return _repositorio_capacitaciones_singleton


def get_organizaciones_repository() -> RepositorioOrganizacionesPort:
    return _repositorio_organizaciones_singleton

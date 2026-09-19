"""src/adapters/gateways/in_memory_registro_capacitaciones_sge_repository.py."""

from src.domain.sge.entities import RegistroCapacitacionSge
from src.domain.sge.ports import RepositorioRegistroCapacitacionesSgePort


class InMemoryRegistroCapacitacionesSgeRepository(RepositorioRegistroCapacitacionesSgePort):
    """Implementación en memoria del repositorio de evidencias de capacitación SGE."""

    def __init__(self) -> None:
        self._registros: list[RegistroCapacitacionSge] = []

    def registrar(self, registro: RegistroCapacitacionSge) -> None:
        self._registros.append(registro)

    def listar_por_usuario(self, usuario_id: str) -> list[RegistroCapacitacionSge]:
        return [r for r in self._registros if r.usuario_id == usuario_id]

    def obtener_por_usuario_y_articulo(self, usuario_id: str, articulo_id: str) -> RegistroCapacitacionSge | None:
        return next(
            (r for r in self._registros if r.usuario_id == usuario_id and r.articulo_id == articulo_id),
            None,
        )

    def listar_todos(self) -> list[RegistroCapacitacionSge]:
        return list(self._registros)

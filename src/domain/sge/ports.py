"""src/domain/sge/ports.py."""

from abc import ABC, abstractmethod

from src.domain.sge.entities import ArticuloSge


class RepositorioDocumentacionSgePort(ABC):
    """Puerto para la persistencia y consulta de documentación del SGE."""

    @abstractmethod
    def listar_todos(self) -> list[ArticuloSge]:
        """Retorna todos los artículos de documentación SGE disponibles."""
        ...

    @abstractmethod
    def listar_por_rol(self, rol: str) -> list[ArticuloSge]:
        """Retorna los artículos de documentación SGE visibles para el rol dado."""
        ...

    @abstractmethod
    def obtener_por_id(self, articulo_id: str) -> ArticuloSge | None:
        """Obtiene un artículo de documentación SGE por su identificador único."""
        ...

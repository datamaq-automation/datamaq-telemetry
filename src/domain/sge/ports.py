"""src/domain/sge/ports.py."""

from abc import ABC, abstractmethod

from src.domain.sge.entities import ArticuloSge, RegistroCapacitacionSge


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


class RepositorioRegistroCapacitacionesSgePort(ABC):
    """Puerto para el registro y auditoría de evidencias de capacitación (ISO 50001 §7.2)."""

    @abstractmethod
    def registrar(self, registro: RegistroCapacitacionSge) -> None:
        """Persiste un nuevo registro de capacitación completada."""
        ...

    @abstractmethod
    def listar_por_usuario(self, usuario_id: str) -> list[RegistroCapacitacionSge]:
        """Retorna las capacitaciones registradas por un usuario específico."""
        ...

    @abstractmethod
    def obtener_por_usuario_y_articulo(self, usuario_id: str, articulo_id: str) -> RegistroCapacitacionSge | None:
        """Obtiene el registro de capacitación de un usuario para un artículo puntual."""
        ...

    @abstractmethod
    def listar_todos(self) -> list[RegistroCapacitacionSge]:
        """Retorna todas las capacitaciones registradas para auditoría."""
        ...

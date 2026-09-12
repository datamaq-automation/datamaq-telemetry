"""src/domain/disponibilidad/ports.py."""
from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.disponibilidad.entities import EventoDisponibilidad, Maquina, ParadaProgramada


class RepositorioMaquinasPort(ABC):
    @abstractmethod
    def obtener_por_id(self, maquina_id: str) -> Maquina | None:
        pass

    @abstractmethod
    def obtener_por_dispositivo_id(self, dispositivo_id: str) -> Maquina | None:
        pass

    @abstractmethod
    def listar(self, organizacion_id: str | None = None) -> list[Maquina]:
        pass

    @abstractmethod
    def guardar(self, maquina: Maquina) -> Maquina:
        pass


class RepositorioEventosDisponibilidadPort(ABC):
    @abstractmethod
    def obtener_por_id(self, evento_id: int) -> EventoDisponibilidad | None:
        pass

    @abstractmethod
    def obtener_evento_abierto(self, maquina_id: str) -> EventoDisponibilidad | None:
        pass

    @abstractmethod
    def listar_por_maquina(self, maquina_id: str, limite: int = 100) -> list[EventoDisponibilidad]:
        pass

    @abstractmethod
    def listar_por_rango(self, maquina_id: str, desde: datetime, hasta: datetime) -> list[EventoDisponibilidad]:
        pass

    @abstractmethod
    def guardar(self, evento: EventoDisponibilidad) -> EventoDisponibilidad:
        pass


class RepositorioParadasProgramadasPort(ABC):
    @abstractmethod
    def guardar(self, parada: ParadaProgramada) -> ParadaProgramada:
        pass

    @abstractmethod
    def listar_por_maquina(self, maquina_id: str) -> list[ParadaProgramada]:
        pass

    @abstractmethod
    def buscar_vigente(self, maquina_id: str, instante: datetime) -> ParadaProgramada | None:
        pass

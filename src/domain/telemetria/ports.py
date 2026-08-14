from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.telemetria.entities import (
    AcumuladoEnergia,
    AlertaDispositivo,
    Dispositivo,
    LecturaInstantanea,
    LogEstadoDispositivo,
    Organizacion,
    Planta,
)
from src.domain.telemetria.value_objects import MacAddress


class RepositorioDispositivosPort(ABC):
    @abstractmethod
    def obtener_por_id(self, dispositivo_id: str) -> Dispositivo | None:
        pass

    @abstractmethod
    def obtener_por_uid(self, uid: MacAddress) -> Dispositivo | None:
        pass

    @abstractmethod
    def listar(self, planta_id: str | None = None) -> list[Dispositivo]:
        pass

    @abstractmethod
    def guardar(self, dispositivo: Dispositivo) -> Dispositivo:
        pass


class RepositorioTelemetriaPort(ABC):
    @abstractmethod
    def guardar_instantanea(self, lectura: LecturaInstantanea) -> None:
        pass

    @abstractmethod
    def guardar_energia(self, acumulado: AcumuladoEnergia) -> None:
        pass

    @abstractmethod
    def guardar_log_estado(self, log: LogEstadoDispositivo) -> None:
        pass

    @abstractmethod
    def guardar_alerta(self, alerta: AlertaDispositivo) -> None:
        pass

    @abstractmethod
    def obtener_ultima_instantanea(self, dispositivo_id: str) -> LecturaInstantanea | None:
        pass

    @abstractmethod
    def obtener_ultimo_acumulado(self, dispositivo_id: str) -> AcumuladoEnergia | None:
        pass

    @abstractmethod
    def listar_instantaneas(
        self,
        dispositivo_id: str,
        limite: int,
        desde: datetime | None = None,
    ) -> list[LecturaInstantanea]:
        pass

    @abstractmethod
    def listar_energias(
        self,
        dispositivo_id: str,
        limite: int,
        desde: datetime | None = None,
    ) -> list[AcumuladoEnergia]:
        pass


class RepositorioOrganizacionesPort(ABC):
    @abstractmethod
    def listar_organizaciones(self) -> list[Organizacion]:
        pass

    @abstractmethod
    def guardar_organizacion(self, org: Organizacion) -> Organizacion:
        pass

    @abstractmethod
    def listar_plantas(self, organizacion_id: str | None = None) -> list[Planta]:
        pass

    @abstractmethod
    def guardar_planta(self, planta: Planta) -> Planta:
        pass


class PublicadorEventosPort(ABC):
    @abstractmethod
    def publicar_telemetria_en_vivo(self, topico: str, datos: dict) -> None:
        pass

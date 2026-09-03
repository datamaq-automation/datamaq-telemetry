from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.telemetria.entities import (
    AcumuladoEnergia,
    AlertaDispositivo,
    Dispositivo,
    DispositivoLayout,
    LecturaInstantanea,
    LogEstadoDispositivo,
    NodoUnifilar,
    Organizacion,
    Planta,
    PlanTelemetria,
    ZonaPlanta,
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
    def contar_por_organizacion(self, organizacion_id: str) -> int:
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

    @abstractmethod
    def listar_acumulados_para_agregacion(
        self,
        dispositivo_id: str,
        desde: datetime | None = None,
    ) -> list[AcumuladoEnergia]:
        pass

    @abstractmethod
    def listar_potencias_para_histograma(
        self,
        dispositivo_id: str,
        desde: datetime,
    ) -> list[float]:
        pass

    @abstractmethod
    def purgar_instantaneas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        pass

    @abstractmethod
    def purgar_energias_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        pass

    @abstractmethod
    def purgar_status_logs_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        pass

    @abstractmethod
    def purgar_alertas_resueltas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        pass

    @abstractmethod
    def listar_alertas(
        self,
        dispositivo_id: str | None = None,
        solo_abiertas: bool = False,
        severidad: str | None = None,
        limite: int = 100,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> list[AlertaDispositivo]:
        pass

    @abstractmethod
    def obtener_alerta_por_id(self, alerta_id: int) -> AlertaDispositivo | None:
        pass


class RepositorioOrganizacionesPort(ABC):
    @abstractmethod
    def obtener_por_id(self, organizacion_id: str) -> Organizacion | None:
        pass

    @abstractmethod
    def listar_organizaciones(self) -> list[Organizacion]:
        pass

    @abstractmethod
    def guardar_organizacion(self, org: Organizacion) -> Organizacion:
        pass

    @abstractmethod
    def obtener_planta_por_id(self, planta_id: str) -> Planta | None:
        pass

    @abstractmethod
    def listar_plantas(self, organizacion_id: str | None = None) -> list[Planta]:
        pass

    @abstractmethod
    def guardar_planta(self, planta: Planta) -> Planta:
        pass

    @abstractmethod
    def obtener_nodos_unifilar(self, planta_id: str) -> list[NodoUnifilar]:
        pass

    @abstractmethod
    def guardar_nodos_unifilar(self, planta_id: str, nodos: list[NodoUnifilar]) -> list[NodoUnifilar]:
        pass

    @abstractmethod
    def obtener_zonas_planta(self, planta_id: str) -> list[ZonaPlanta]:
        pass

    @abstractmethod
    def obtener_dispositivos_layout(self, planta_id: str) -> list[DispositivoLayout]:
        pass

    @abstractmethod
    def guardar_layout_planta(
        self,
        planta_id: str,
        plano_svg_url: str | None,
        zonas: list[ZonaPlanta],
        dispositivos: list[DispositivoLayout],
    ) -> None:
        pass


class RepositorioPlanesPort(ABC):
    @abstractmethod
    def listar_planes(self) -> list[PlanTelemetria]:
        pass

    @abstractmethod
    def obtener_por_id(self, plan_id: str) -> PlanTelemetria | None:
        pass

    @abstractmethod
    def guardar_plan(self, plan: PlanTelemetria) -> PlanTelemetria:
        pass


class PublicadorEventosPort(ABC):
    @abstractmethod
    def publicar_telemetria_en_vivo(self, topico: str, datos: dict) -> None:
        pass


class BufferTelemetriaEnVivoPort(ABC):
    @abstractmethod
    def obtener(self, dispositivo_id: str) -> list[dict]:
        pass


class LoggerPort(ABC):
    @abstractmethod
    def info(self, evento: str, **kwargs: object) -> None:
        pass

    @abstractmethod
    def warning(self, evento: str, **kwargs: object) -> None:
        pass

    @abstractmethod
    def error(self, evento: str, **kwargs: object) -> None:
        pass

    @abstractmethod
    def debug(self, evento: str, **kwargs: object) -> None:
        pass

"""src/domain/telemetria/ports.py."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
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
    Suscripcion,
    ZonaPlanta,
)
from src.domain.telemetria.value_objects import EstadoDispositivo, LecturaPotenciaTemporal, MacAddress


class RepositorioDispositivosPort(ABC):
    @abstractmethod
    def obtener_por_id(self, dispositivo_id: str) -> Dispositivo | None:
        pass

    @abstractmethod
    def obtener_por_uid(self, uid: MacAddress) -> Dispositivo | None:
        pass

    @abstractmethod
    def listar(self, planta_id: str | None = None, organizacion_id: str | None = None) -> list[Dispositivo]:
        pass

    @abstractmethod
    def contar_por_organizacion(self, organizacion_id: str) -> int:
        pass

    @abstractmethod
    def guardar(self, dispositivo: Dispositivo) -> Dispositivo:
        pass

    @abstractmethod
    def actualizar_heartbeat(
        self,
        dispositivo_id: str,
        estado: EstadoDispositivo,
        visto_por_ultima_vez: datetime,
        numero_serie: str | None = None,
        version_fw: str | None = None,
        version_hw: str | None = None,
    ) -> None:
        """Actualiza solo el estado operativo del heartbeat (online + último visto + firmware
        opcional). Nunca toca campos administrativos como planta_id/nombre/modelo: a diferencia
        de `guardar()`, este método existe justamente para que el refresco de heartbeat de alta
        frecuencia no pueda pisar una reasignación de planta hecha por fuera del proceso de
        ingesta mientras el dispositivo sigue transmitiendo.
        """
        pass


class RepositorioTelemetriaPort(ABC):
    @abstractmethod
    def guardar_instantanea(self, lectura: LecturaInstantanea) -> None:
        pass

    @abstractmethod
    def guardar_energia(self, acumulado: AcumuladoEnergia, prioritario: bool = True) -> None:
        """Persiste un acumulado de energía.

        ``prioritario=True`` (fuente ``energyio``, D1) sobreescribe cualquier fila
        existente para el mismo (device_id, recorded_at). ``prioritario=False``
        (fuente ``acc``, respaldo) solo inserta si no había fila — nunca pisa un
        valor de la fuente prioritaria que haya llegado antes.
        """
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

    def iterar_instantaneas(
        self,
        dispositivo_id: str,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        limite: int = 10000,
        chunk_size: int = 500,
    ) -> Iterator[LecturaInstantanea]:
        items = self.listar_instantaneas(dispositivo_id, limite=limite, desde=desde)
        if hasta:
            items = [i for i in items if i.registrado_en <= hasta]
        yield from items

    @abstractmethod
    def listar_energias(
        self,
        dispositivo_id: str,
        limite: int,
        desde: datetime | None = None,
    ) -> list[AcumuladoEnergia]:
        pass

    @abstractmethod
    def listar_ultimos_acumulados_por_periodo(
        self,
        dispositivo_id: str,
        desde: datetime | None = None,
        granularidad: str = "day",
        zona: str = "UTC",
    ) -> list[AcumuladoEnergia]:
        """Un acumulado por periodo (el último recibido), no la serie completa.

        Reemplaza la carga de la serie cruda para agregación: el "último del
        periodo" se resuelve en SQL (ROW_NUMBER particionado por periodo local),
        de modo que un dispositivo con meses de datos a cadencia de segundos
        devuelve como máximo un puñado de filas en vez de cientos de miles.
        """
        pass

    @abstractmethod
    def listar_potencias_para_histograma(
        self,
        dispositivo_id: str,
        desde: datetime,
        limite: int | None = None,
    ) -> list[LecturaPotenciaTemporal]:
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
    """Lectura del modelo declarativo de activos (`data/organizaciones.yml`).

    Solo lectura a propósito: la estructura de planta se modifica por commit al
    YAML, no por API. No hay `guardar_*`.
    """

    @abstractmethod
    def obtener_por_id(self, organizacion_id: str) -> Organizacion | None:
        pass

    @abstractmethod
    def listar_organizaciones(self) -> list[Organizacion]:
        pass

    @abstractmethod
    def obtener_planta_por_id(self, planta_id: str) -> Planta | None:
        pass

    @abstractmethod
    def listar_plantas(self, organizacion_id: str | None = None) -> list[Planta]:
        pass

    @abstractmethod
    def obtener_nodos_unifilar(self, planta_id: str) -> list[NodoUnifilar]:
        pass

    @abstractmethod
    def obtener_zonas_planta(self, planta_id: str) -> list[ZonaPlanta]:
        pass

    @abstractmethod
    def obtener_dispositivos_layout(self, planta_id: str) -> list[DispositivoLayout]:
        pass


class RepositorioSuscripcionesPort(ABC):
    @abstractmethod
    def obtener_por_organizacion(self, organizacion_id: str) -> Suscripcion | None:
        pass

    @abstractmethod
    def guardar(self, suscripcion: Suscripcion) -> Suscripcion:
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


class NotificadorAlertasPort(ABC):
    @abstractmethod
    def notificar_alerta_critica(
        self,
        alerta: AlertaDispositivo,
        dispositivo: Dispositivo,
        destinatarios: list[str],
    ) -> bool:
        pass

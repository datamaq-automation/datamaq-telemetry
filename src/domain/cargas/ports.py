from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.cargas.entities import (
    CampanaCaracterizacion,
    Carga,
    IntervaloActividadCarga,
)
from src.domain.cargas.value_objects import MuestraCampana
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal


class RepositorioCargasPort(ABC):
    @abstractmethod
    def obtener_por_id(self, carga_id: str) -> Carga | None:
        pass

    @abstractmethod
    def obtener_por_nombre(self, dispositivo_id: str, nombre: str) -> Carga | None:
        pass

    @abstractmethod
    def listar_por_dispositivo(self, dispositivo_id: str, solo_activas: bool = False) -> list[Carga]:
        pass

    @abstractmethod
    def listar(self) -> list[Carga]:
        pass

    @abstractmethod
    def guardar(self, carga: Carga) -> Carga:
        pass


class RepositorioSeriePotenciaPort(ABC):
    """Lectura proyectada de la serie de potencia para análisis de cargas.

    Es un read model propio del contexto y no un método más del repositorio de
    telemetría: acá se leen P **y Q** (el eje que separa cargas resistivas de motores),
    se recorren ventanas potencialmente largas, y solo interesan cuatro columnas de una
    tabla de decenas. Materializar `LecturaInstantanea` completas sería caro e inútil.
    """

    @abstractmethod
    def listar_serie_potencia(
        self,
        dispositivo_id: str,
        desde: datetime,
        hasta: datetime | None = None,
        limite: int | None = None,
    ) -> list[LecturaPotenciaTemporal]:
        pass

    @abstractmethod
    def obtener_energia_consumida_kwh(self, dispositivo_id: str, desde: datetime, hasta: datetime) -> float | None:
        """Consumo real del período según el contador acumulado.

        Es la única cifra exacta disponible: integrar la serie instantánea de 5 minutos
        daría un sesgo sistemático, porque entre muestra y muestra puede haber prendido
        y apagado cualquier cosa.
        """
        pass


class RepositorioCampanasPort(ABC):
    """Campañas y sus muestras de alta resolución.

    `agregar_muestra` se llama desde el camino de ingesta MQTT, una vez por lectura y a
    caudal de ráfaga: tiene que ser idempotente ante el redelivery de QoS 1 y devolver
    si la muestra era nueva, para poder llevar la cuenta sin releer la tabla.
    """

    @abstractmethod
    def obtener_por_id(self, campana_id: str) -> CampanaCaracterizacion | None:
        pass

    @abstractmethod
    def obtener_en_curso_por_dispositivo(self, dispositivo_id: str) -> CampanaCaracterizacion | None:
        pass

    @abstractmethod
    def listar_en_curso(self) -> list[CampanaCaracterizacion]:
        pass

    @abstractmethod
    def listar_por_carga(self, carga_id: str) -> list[CampanaCaracterizacion]:
        pass

    @abstractmethod
    def guardar(self, campana: CampanaCaracterizacion) -> CampanaCaracterizacion:
        pass

    @abstractmethod
    def agregar_muestra(self, campana_id: str, muestra: MuestraCampana) -> bool:
        pass

    @abstractmethod
    def listar_muestras(self, campana_id: str) -> list[MuestraCampana]:
        pass


class ComandoRafagaPort(ABC):
    """Salida hacia el medidor físico para pedirle publicación a alta frecuencia.

    Existe como puerto y no como una llamada directa al listener MQTT porque el caso de
    uso vive en `application/` y no puede conocer `infrastructure/`. El adaptador lo
    implementa sobre `realtime_sync_mode`, cuyo `time_s` es la **duración** de la
    ráfaga: hay que renovarla periódicamente mientras dure la campaña.
    """

    @abstractmethod
    def activar_rafaga(self, device_uid: str, segundos: int) -> bool:
        pass


class RepositorioIntervalosActividadPort(ABC):
    """Intervalos de actividad atribuidos, con su historial de correcciones humanas."""

    @abstractmethod
    def obtener_por_id(self, intervalo_id: int) -> IntervaloActividadCarga | None:
        pass

    @abstractmethod
    def listar_por_dispositivo(
        self, dispositivo_id: str, desde: datetime, hasta: datetime
    ) -> list[IntervaloActividadCarga]:
        pass

    @abstractmethod
    def listar_por_carga(self, carga_id: str, limite: int = 100) -> list[IntervaloActividadCarga]:
        pass

    @abstractmethod
    def guardar(self, intervalo: IntervaloActividadCarga) -> IntervaloActividadCarga:
        pass

    @abstractmethod
    def reemplazar_ventana(
        self, dispositivo_id: str, desde: datetime, hasta: datetime, intervalos: list[IntervaloActividadCarga]
    ) -> int:
        """Deja la ventana con exactamente estos intervalos, **sin tocar las correcciones humanas**.

        Devuelve cuántos se escribieron. Esas filas corregidas a mano son el dataset
        etiquetado del proyecto: que el batch las pisara al reprocesar destruiría lo
        único que ninguna regla puede regenerar.
        """
        pass

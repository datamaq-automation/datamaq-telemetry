"""src/domain/maquinas/ports.py."""

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.maquinas.entities import (
    EnsayoCaracterizacion,
    IntervaloActividadMáquina,
    Máquina,
)
from src.domain.maquinas.value_objects import MuestraCampana
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal


class RepositorioMáquinasPort(ABC):
    @abstractmethod
    def obtener_por_id(self, maquina_id: str) -> Máquina | None:
        pass

    @abstractmethod
    def obtener_por_nombre(self, dispositivo_id: str, nombre: str) -> Máquina | None:
        pass

    @abstractmethod
    def listar_por_dispositivo(self, dispositivo_id: str, solo_activas: bool = False) -> list[Máquina]:
        pass

    @abstractmethod
    def listar(self) -> list[Máquina]:
        pass

    @abstractmethod
    def guardar(self, maquina: Máquina) -> Máquina:
        pass


class RepositorioSeriePotenciaPort(ABC):
    """Lectura proyectada de la serie de potencia para análisis de máquinas.

    Es un read model propio del contexto y no un método más del repositorio de
    telemetría: acá se leen P **y Q** (el eje que separa máquinas resistivas de motores),
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


class RepositorioEnsayosPort(ABC):
    """Ensayos de caracterización y sus muestras de alta resolución.

    `agregar_muestra` se llama desde el camino de ingesta MQTT, una vez por lectura y a
    caudal de ráfaga: tiene que ser idempotente ante el redelivery de QoS 1 y devolver
    si la muestra era nueva, para poder llevar la cuenta sin releer la tabla.
    """

    @abstractmethod
    def obtener_por_id(self, ensayo_id: str) -> EnsayoCaracterizacion | None:
        pass

    @abstractmethod
    def obtener_en_curso_por_dispositivo(self, dispositivo_id: str) -> EnsayoCaracterizacion | None:
        pass

    @abstractmethod
    def listar_en_curso(self) -> list[EnsayoCaracterizacion]:
        pass

    @abstractmethod
    def listar_por_maquina(self, maquina_id: str) -> list[EnsayoCaracterizacion]:
        pass

    @abstractmethod
    def guardar(self, ensayo: EnsayoCaracterizacion) -> EnsayoCaracterizacion:
        pass

    @abstractmethod
    def agregar_muestra(self, ensayo_id: str, muestra: MuestraCampana) -> bool:
        pass

    @abstractmethod
    def listar_muestras(self, ensayo_id: str) -> list[MuestraCampana]:
        pass


class ComandoRafagaPort(ABC):
    """Salida hacia el medidor físico para pedirle publicación a alta frecuencia.

    Existe como puerto y no como una llamada directa al listener MQTT porque el caso de
    uso vive en `application/` y no puede conocer `infrastructure/`. El adaptador lo
    implementa sobre `realtime_sync_mode`, cuyo `time_s` es la **duración** de la
    ráfaga: hay que renovarla periódicamente mientras dure el ensayo.
    """

    @abstractmethod
    def activar_rafaga(self, device_uid: str, segundos: int) -> bool:
        pass


class RepositorioIntervalosActividadPort(ABC):
    """Intervalos de actividad atribuidos, con su historial de correcciones humanas."""

    @abstractmethod
    def obtener_por_id(self, intervalo_id: int) -> IntervaloActividadMáquina | None:
        pass

    @abstractmethod
    def listar_por_dispositivo(
        self, dispositivo_id: str, desde: datetime, hasta: datetime
    ) -> list[IntervaloActividadMáquina]:
        pass

    @abstractmethod
    def listar_por_maquina(self, maquina_id: str, limite: int = 100) -> list[IntervaloActividadMáquina]:
        pass

    @abstractmethod
    def guardar(self, intervalo: IntervaloActividadMáquina) -> IntervaloActividadMáquina:
        pass

    @abstractmethod
    def reemplazar_ventana(
        self, dispositivo_id: str, desde: datetime, hasta: datetime, intervalos: list[IntervaloActividadMáquina]
    ) -> int:
        """Deja la ventana con exactamente estos intervalos, **sin tocar las correcciones humanas**.

        Devuelve cuántos se escribieron. Esas filas corregidas a mano son el dataset
        etiquetado del proyecto: que el batch las pisara al reprocesar destruiría lo
        único que ninguna regla puede regenerar.
        """
        pass


class DescubridorMáquinasPort(ABC):
    """Puerto para descubrir máquinas en una serie agregada mediante un servicio externo."""

    @abstractmethod
    def descubrir(self, medidor: str, desde: datetime, hasta: datetime) -> list:
        """Descubre candidatas de máquinas en el rango temporal.

        Lanza DescubridorNoDisponibleError si el servicio no responde o responde != 200.
        """
        pass

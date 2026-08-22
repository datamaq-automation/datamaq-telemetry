from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from src.domain.telemetria.value_objects import (
    Corriente,
    EnergiaActiva,
    EnergiaReactiva,
    EstadoDispositivo,
    FactorPotencia,
    MacAddress,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    SeveridadAlerta,
    Tension,
    VisibilidadPlan,
)


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PlanTelemetria:
    id: str
    nombre: str
    descripcion: str
    precio_mensual_ars: Decimal
    visibilidad: VisibilidadPlan
    retencion_dias: int
    granularidad_minutos: int
    max_dispositivos: int
    canales_notificacion: list[str]
    creado_en: datetime = field(default_factory=ahora_utc)
    actualizado_en: datetime = field(default_factory=ahora_utc)


@dataclass
class Organizacion:
    id: str
    nombre: str
    plan_id: str | None = None
    cuit: str | None = None
    email_contacto: str | None = None
    telefono_contacto: str | None = None
    creado_en: datetime = field(default_factory=ahora_utc)
    actualizado_en: datetime = field(default_factory=ahora_utc)


@dataclass
class Planta:
    id: str
    organizacion_id: str
    nombre: str
    direccion: str | None = None
    latitud: float | None = None
    longitud: float | None = None
    creado_en: datetime = field(default_factory=ahora_utc)
    actualizado_en: datetime = field(default_factory=ahora_utc)


@dataclass
class Dispositivo:
    id: str
    device_uid: MacAddress
    nombre: str
    modelo: str = "SmartPlus"
    planta_id: str | None = None
    numero_serie: str | None = None
    version_hw: str | None = None
    version_fw: str | None = None
    ubicacion_tag: str | None = None
    esta_activo: bool = True
    estado: EstadoDispositivo = EstadoDispositivo.OFFLINE
    visto_por_ultima_vez: datetime | None = None
    tipo_instalacion: str = "CONSUMO"
    fases_con_ti: str = "R,S,T"
    creado_en: datetime = field(default_factory=ahora_utc)
    actualizado_en: datetime = field(default_factory=ahora_utc)

    def marcar_online(self, timestamp: datetime | None = None) -> None:
        self.estado = EstadoDispositivo.ONLINE
        self.visto_por_ultima_vez = timestamp or ahora_utc()

    def marcar_offline(self) -> None:
        self.estado = EstadoDispositivo.OFFLINE


@dataclass(frozen=True)
class MedicionFase:
    tension: Tension | None = None
    corriente: Corriente | None = None
    potencia_activa: PotenciaActiva | None = None
    potencia_reactiva: PotenciaReactiva | None = None
    potencia_aparente: PotenciaAparente | None = None
    factor_potencia: FactorPotencia | None = None


@dataclass(frozen=True)
class LecturaInstantanea:
    id: int | None
    dispositivo_id: str
    registrado_en: datetime
    fase_r: MedicionFase
    fase_s: MedicionFase
    fase_t: MedicionFase
    potencia_activa_total: PotenciaActiva | None = None
    potencia_reactiva_total: PotenciaReactiva | None = None
    potencia_aparente_total: PotenciaAparente | None = None
    factor_potencia_total: FactorPotencia | None = None
    desbalance_tension_porcentaje: float | None = None
    corriente_neutro_estimada: Corriente | None = None
    voltage_linea_V: float | None = None


@dataclass(frozen=True)
class AcumuladoEnergia:
    id: int | None
    dispositivo_id: str
    registrado_en: datetime
    energia_activa_neta: EnergiaActiva | None = None
    energia_reactiva_neta: EnergiaReactiva | None = None
    energia_activa_importada: EnergiaActiva | None = None
    energia_activa_exportada: EnergiaActiva | None = None
    energia_reactiva_importada: EnergiaReactiva | None = None
    energia_reactiva_exportada: EnergiaReactiva | None = None


@dataclass(frozen=True)
class LogEstadoDispositivo:
    id: int | None
    dispositivo_id: str
    registrado_en: datetime
    wifi_rssi_dbm: int | None = None
    wifi_calidad: int | None = None
    direccion_ip: str | None = None
    tiempo_activo_segundos: int | None = None
    payload_bruto: dict[str, Any] | None = None


@dataclass
class AlertaDispositivo:
    id: int | None
    dispositivo_id: str
    tipo_alerta: str
    severidad: SeveridadAlerta
    mensaje: str
    esta_resuelta: bool = False
    disparada_en: datetime = field(default_factory=ahora_utc)
    resuelta_en: datetime | None = None

    def marcar_resuelta(self, timestamp: datetime | None = None) -> None:
        self.esta_resuelta = True
        self.resuelta_en = timestamp or ahora_utc()

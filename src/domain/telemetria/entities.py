"""src/domain/telemetria/entities.py."""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from src.domain.telemetria.value_objects import (
    CoordenadasZona,
    Corriente,
    EnergiaActiva,
    EnergiaReactiva,
    EstadoDispositivo,
    FactorPotencia,
    MacAddress,
    ModoFreeTier,
    PosicionLayout,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    SeveridadAlerta,
    Tension,
    TipoNodoUnifilar,
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
    """Identidad del cliente (ISA-95 nivel 4). Dato maestro: vive en `data/organizaciones.yml`.

    El estado comercial (plan, vencimiento PRO, modo free) es `Suscripcion`, no
    está acá: tiene fecha de vencimiento y se gestiona en MySQL, no por commit.
    """

    id: str
    nombre: str
    cuit: str | None = None
    email_contacto: str | None = None
    telefono_contacto: str | None = None
    creado_en: datetime = field(default_factory=ahora_utc)
    actualizado_en: datetime = field(default_factory=ahora_utc)


@dataclass
class Suscripcion:
    """Estado comercial de una organización (tabla `organizations` en MySQL).

    Sin fila para una organización se asume `por_defecto`: free tier privado,
    sin plan y sin PRO vigente — lo mismo que hoy da el YAML cuando no declara nada.
    """

    organizacion_id: str
    plan_id: str | None = None
    pro_vence_en: datetime | None = None
    modo_free: ModoFreeTier = ModoFreeTier.PRIVADO_BASICO
    actualizado_en: datetime = field(default_factory=ahora_utc)

    @classmethod
    def por_defecto(cls, organizacion_id: str) -> "Suscripcion":
        return cls(organizacion_id=organizacion_id)


@dataclass
class Planta:
    id: str
    organizacion_id: str
    nombre: str
    direccion: str | None = None
    latitud: float | None = None
    longitud: float | None = None
    layout_svg_url: str | None = None
    creado_en: datetime = field(default_factory=ahora_utc)
    actualizado_en: datetime = field(default_factory=ahora_utc)


@dataclass
class NodoUnifilar:
    id: str
    planta_id: str
    nombre: str
    tipo: TipoNodoUnifilar
    tension_nominal_v: float
    parent_id: str | None = None
    device_id: str | None = None
    capacidad_nominal_kva: float | None = None
    potencia_nominal_kw: float | None = None
    uso_significativo: bool = False
    categoria_uso: str | None = None
    variable_relevante: str | None = None
    orden: int = 0
    # Contrato con la distribuidora: solo tiene sentido en la `acometida` (punto de
    # suministro). Los medidores aguas abajo lo heredan por el árbol.
    categoria_tarifaria: str | None = None
    penalizacion_reactiva_aplica: bool | None = None
    creado_en: datetime = field(default_factory=ahora_utc)
    actualizado_en: datetime = field(default_factory=ahora_utc)


@dataclass(frozen=True)
class InstalacionMedidor:
    """Datos de puesta en servicio de un medidor, declarados en el YAML (dato maestro).

    Cada campo es opcional: solo lo declarado gobierna; lo no declarado sigue
    saliendo de MySQL. Un campo declarado no puede modificarse por `PATCH`.
    """

    dispositivo_id: str
    tag_ubicacion: str | None = None
    tipo_instalacion: str | None = None
    fases_con_ti: str | None = None

    def campos_declarados(self) -> set[str]:
        return {
            campo
            for campo, valor in (
                ("ubicacion_tag", self.tag_ubicacion),
                ("tipo_instalacion", self.tipo_instalacion),
                ("fases_con_ti", self.fases_con_ti),
            )
            if valor is not None
        }


@dataclass
class ZonaPlanta:
    id: str
    planta_id: str
    nombre: str
    coordenadas: CoordenadasZona
    creado_en: datetime = field(default_factory=ahora_utc)
    actualizado_en: datetime = field(default_factory=ahora_utc)


@dataclass
class DispositivoLayout:
    id: str
    planta_id: str
    device_id: str
    posicion: PosicionLayout
    zona_id: str | None = None
    creado_en: datetime = field(default_factory=ahora_utc)
    actualizado_en: datetime = field(default_factory=ahora_utc)


@dataclass
class UnifilarPlanta:
    planta_id: str
    nombre_planta: str
    nodos: list[NodoUnifilar] = field(default_factory=list)


@dataclass
class LayoutPlanta:
    planta_id: str
    nombre_planta: str
    plano_svg_url: str | None = None
    zonas: list[ZonaPlanta] = field(default_factory=list)
    dispositivos: list[DispositivoLayout] = field(default_factory=list)


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
    ct_fases_invertidas: str = ""
    potencia_contratada_kw: float | None = None
    tarifa: str | None = None
    categoria_tarifaria: str | None = "T2"
    penalizacion_reactiva_aplica: bool = True
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
    thd_v_porcentaje: float | None = None
    thd_i_porcentaje: float | None = None
    thd_v_pct: float | None = None
    thd_i_pct: float | None = None


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
    tension_neutro_estimada: float | None = None
    thd_v_promedio_porcentaje: float | None = None
    thd_i_total_porcentaje: float | None = None
    thd_v_promedio_pct: float | None = None
    thd_i_total_pct: float | None = None


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
    fuente: str | None = None
    """Subtópico MQTT de origen: "energyio" (registro total del equipo, prioritario)
    o "acc" (suma de fases, respaldo). None para lecturas sin fuente rastreada."""


@dataclass(frozen=True)
class EnergiaAgregada:
    """Consumo de energía de un periodo (día o mes), calculado como delta del contador acumulado.

    ``energia_activa_neta_kwh`` es ``None`` en el primer periodo, que no tiene un
    periodo anterior como referencia: la UI omite esa barra en vez de inventar un valor.
    """

    periodo: date
    energia_activa_neta_kwh: float | None = None


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
    fase: str | None = None
    valor_medido: float | None = None
    valor_umbral: float | None = None
    unidad: str | None = None
    categoria: str | None = None
    observaciones: str | None = None

    @property
    def duracion_segundos(self) -> float | None:
        if self.resuelta_en and self.disparada_en:
            return max(0.0, round((self.resuelta_en - self.disparada_en).total_seconds(), 1))
        return None

    def marcar_resuelta(self, timestamp: datetime | None = None, observaciones: str | None = None) -> None:
        self.esta_resuelta = True
        self.resuelta_en = timestamp or ahora_utc()
        if observaciones is not None:
            self.observaciones = observaciones

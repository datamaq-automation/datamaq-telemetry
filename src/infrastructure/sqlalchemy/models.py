"""src/infrastructure/sqlalchemy/models.py."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.infrastructure.sqlalchemy.types import UtcDateTime


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


def generate_uuid() -> str:
    return str(uuid.uuid4())


class OrganizationModel(Base):
    """Suscripción (estado comercial) de una organización.

    La identidad (nombre, CUIT, contacto) vive en `data/organizaciones.yml`; acá
    queda el `id` como ancla de las FK de `users`/`facilities` y lo que tiene
    fecha de vencimiento: plan, PRO y modo free.
    """

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    plan_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    pro_expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    free_tier_mode: Mapped[str] = mapped_column(String(30), default="PRIVADO_BASICO", nullable=False)
    es_cooperativa: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)

    plan: Mapped[Optional["PlanModel"]] = relationship()
    facilities: Mapped[list["FacilityModel"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class FacilityModel(Base):
    __tablename__ = "facilities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 8), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(11, 8), nullable=True)
    layout_svg_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)

    organization: Mapped["OrganizationModel"] = relationship(back_populates="facilities")
    devices: Mapped[list["DeviceModel"]] = relationship(back_populates="facility")


class DeviceModel(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    facility_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True
    )
    device_uid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    serial_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(100), default="Nuevo Powermeter", nullable=False)
    model: Mapped[str] = mapped_column(String(50), default="SmartPlus", nullable=False)
    hw_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fw_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tag_location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    esta_activo: Mapped[bool] = mapped_column("is_active", default=True, nullable=False)
    estado: Mapped[str] = mapped_column("status", String(20), default="OFFLINE", nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    installation_type: Mapped[str] = mapped_column(String(30), default="CONSUMO", nullable=False)
    phases_with_ct: Mapped[str] = mapped_column(String(20), default="R,S,T", nullable=False)
    ct_inverted_phases: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    ct_phase_angle_offsets: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    categoria_tarifaria: Mapped[str] = mapped_column(String(10), default="T2", nullable=False)
    penalizacion_reactiva_aplica: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)

    facility: Mapped[Optional["FacilityModel"]] = relationship(back_populates="devices")
    instantaneous_readings: Mapped[list["TelemetryInstantaneousModel"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    energy_readings: Mapped[list["TelemetryEnergyModel"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    status_logs: Mapped[list["DeviceStatusLogModel"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["DeviceAlertModel"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    auditoria_cambios_ti: Mapped[list["AuditoriaChangesTIModel"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class TelemetryInstantaneousModel(Base):
    __tablename__ = "telemetry_instantaneous"
    __table_args__ = (
        Index("idx_telemetry_inst_dev_time", "device_id", "recorded_at"),
        Index("idx_telemetry_inst_time", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    # Fase R
    voltage_r: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    current_r: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    active_power_r: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    reactive_power_r: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    apparent_power_r: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    power_factor_r: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)

    # Fase S
    voltage_s: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    current_s: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    active_power_s: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    reactive_power_s: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    apparent_power_s: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    power_factor_s: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)

    # Fase T
    voltage_t: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    current_t: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    active_power_t: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    reactive_power_t: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    apparent_power_t: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    power_factor_t: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)

    # Totales
    total_active_power: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_reactive_power: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_apparent_power: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_power_factor: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    desbalance_tension_porcentaje: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    current_n: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    voltage_linea_V: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    tension_neutro_estimada: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)

    # Distorsión Armónica Total (THD)
    thd_v_r: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    thd_i_r: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    thd_v_s: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    thd_i_s: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    thd_v_t: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    thd_i_t: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    thd_v_promedio_porcentaje: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    thd_i_total_porcentaje: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    es_dato_confiable: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)

    device: Mapped["DeviceModel"] = relationship(back_populates="instantaneous_readings")


class TelemetryEnergyModel(Base):
    __tablename__ = "telemetry_energy"
    __table_args__ = (
        Index("idx_telemetry_energy_dev_time", "device_id", "recorded_at"),
        Index("idx_telemetry_energy_time", "recorded_at"),
        # Un solo acumulado por medidor e instante, sin importar qué subtópico lo
        # publicó (D1): acc y energyio del mismo timestamp compiten por la misma
        # fila, no coexisten. La prioridad entre ambos la resuelve guardar_energia
        # (upsert si prioritario, INSERT IGNORE si no) — ver WP2. Índice único (no
        # UniqueConstraint) por portabilidad: SQLite, donde corren los tests de
        # migraciones, no soporta ADD CONSTRAINT fuera de batch mode.
        Index("uq_energy_dev_time", "device_id", "recorded_at", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    net_active_energy_kwh: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    net_reactive_energy_kvarh: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    imported_active_energy_kwh: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    exported_active_energy_kwh: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    imported_reactive_energy_kvarh: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    exported_reactive_energy_kvarh: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    """Subtópico MQTT de origen ("energyio" prioritario, "acc" respaldo, ver D1).
    NULL en filas anteriores a WP2, que no rastreaban esto."""

    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)

    device: Mapped["DeviceModel"] = relationship(back_populates="energy_readings")


class DeviceStatusLogModel(Base):
    __tablename__ = "device_status_logs"
    __table_args__ = (
        Index("idx_device_status_dev_time", "device_id", "recorded_at"),
        Index("idx_device_status_time", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    wifi_rssi_dbm: Mapped[int | None] = mapped_column(nullable=True)
    wifi_calidad: Mapped[int | None] = mapped_column(nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)

    device: Mapped["DeviceModel"] = relationship(back_populates="status_logs")


class DeviceAlertModel(Base):
    __tablename__ = "device_alerts"
    __table_args__ = (
        Index("idx_alerts_dev_resolved", "device_id", "is_resolved"),
        Index("idx_alerts_resolved_purge", "is_resolved", "resolved_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(
        Enum("INFO", "WARNING", "CRITICAL", name="alert_severity"), default="WARNING", nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(default=False, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    phase: Mapped[str | None] = mapped_column(String(10), nullable=True)
    measured_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    threshold_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_detected_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    occurrences: Mapped[int] = mapped_column(default=1, server_default="1", nullable=False)

    device: Mapped["DeviceModel"] = relationship(back_populates="alerts")


class MachineModel(Base):
    __tablename__ = "machines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    on_threshold_w: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    persistence_readings: Mapped[int] = mapped_column(default=2, nullable=False)
    persistence_seconds: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("60.0"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)

    device: Mapped["DeviceModel"] = relationship()


class MachineAvailabilityEventModel(Base):
    __tablename__ = "machine_availability_events"
    __table_args__ = (Index("idx_machine_availability_machine_open", "machine_id", "end_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    machine_id: Mapped[str] = mapped_column(String(36), ForeignKey("machines.id", ondelete="CASCADE"), nullable=False)
    state: Mapped[str] = mapped_column(String(10), nullable=False)
    stop_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    start_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    avg_power_w: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="REGLA", nullable=False)
    corrected_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    corrected_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    machine: Mapped["MachineModel"] = relationship()


class ScheduledStopModel(Base):
    __tablename__ = "scheduled_stops"
    __table_args__ = (Index("idx_scheduled_stops_machine_range", "machine_id", "start_at", "end_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    machine_id: Mapped[str] = mapped_column(String(36), ForeignKey("machines.id", ondelete="CASCADE"), nullable=False)
    start_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    reason: Mapped[str] = mapped_column(String(250), nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)

    machine: Mapped["MachineModel"] = relationship()


class PlanModel(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    monthly_price_ars: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), default="PUBLICO", nullable=False)
    retention_days: Mapped[int] = mapped_column(nullable=False)
    granularity_minutes: Mapped[int] = mapped_column(nullable=False)
    max_devices: Mapped[int] = mapped_column(nullable=False)
    notification_channels: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)


class DispositivoConfiableModel(Base):
    __tablename__ = "dispositivos_confiables"
    __table_args__ = (
        Index("idx_dispositivos_confiables_usuario", "usuario_id"),
        Index("idx_dispositivos_confiables_hash", "token_hash", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    usuario_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    nombre_dispositivo: Mapped[str | None] = mapped_column(String(150), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    ip_origen: Mapped[str] = mapped_column(String(45), default="", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    ultimo_acceso_en: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    expira_en: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    revocado: Mapped[bool] = mapped_column(default=False, nullable=False)


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="operador", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    totp_backup_codes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    sesiones_revocadas_antes_de: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)


class UserFacilityAccessModel(Base):
    """Asignación explícita usuario ↔ planta (R-02 del frontend).

    `facility_id` no lleva FK: las plantas son SSOT del YAML declarativo
    (`data/organizaciones.yml`), igual que `users.organization_id` se valida
    contra el YAML en startup y no contra `facilities`.
    """

    __tablename__ = "user_facility_access"
    __table_args__ = (Index("idx_user_facility_access_facility", "facility_id"),)

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    facility_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    can_switch: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)


class WebhookEventModel(Base):
    """Idempotencia de webhooks de proveedores de pago (Mercado Pago): un `event_id`
    reenviado por el proveedor no debe disparar dos veces la misma activación/baja."""

    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_events_provider_event"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    event_id: Mapped[str] = mapped_column(String(100), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)


class AuditLogModel(Base):
    """Registro inmutable append-only de auditoría (ISO 27001 A.8.15 / Ley 25.326)."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    registrado_en: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)

    # Sujeto (Actor)
    actor_usuario_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    actor_user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Evento
    categoria: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    accion: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resultado: Mapped[str] = mapped_column(String(20), nullable=False)

    # Objeto de la Acción
    recurso_tipo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    recurso_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Metadatos del Cambio (Diff seguro — PROHIBIDO registrar passwords o secrets)
    metadatos: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_audit_actor_fecha", "actor_usuario_id", "registrado_en"),
        Index("idx_audit_recurso", "recurso_tipo", "recurso_id"),
    )


class TelemetriaAnomaliaModel(Base):
    """Flag de coherencia baja en telemetría instantánea (Capa 1: detección ingesta)."""

    __tablename__ = "telemetria_anomalias"
    __table_args__ = (
        Index("idx_anomalias_device_recorded", "device_id", "recorded_at"),
        Index("idx_anomalias_estado", "estado"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    error_s: Mapped[float] = mapped_column(nullable=False, comment="Error % entre S medida y S teórica")
    flag_tipo: Mapped[str] = mapped_column(
        Enum("coherencia_baja", "degradacion", "otros", name="anomalia_tipo"), nullable=False
    )
    contador_consecutivos: Mapped[int] = mapped_column(nullable=False, default=1)
    estado: Mapped[str] = mapped_column(
        Enum("active", "resolved", name="anomalia_estado"), nullable=False, default="active"
    )
    creado_en: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)


class DispositivoDiagnosticoModel(Base):
    """Histórico de diagnósticos TI por dispositivo (Capa 3: job semanal)."""

    __tablename__ = "dispositivo_diagnosticos"
    __table_args__ = (Index("idx_diagnosticos_device_ejecutado", "device_id", "ejecutado_en"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    ejecutado_en: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    config_actual: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="R,S,T o S,R,T")
    config_actual_invertido: Mapped[bool | None] = mapped_column(nullable=True)
    top_candidato: Mapped[str | None] = mapped_column(String(50), nullable=True)
    top_candidato_invertido: Mapped[bool | None] = mapped_column(nullable=True)
    top_score: Mapped[float | None] = mapped_column(nullable=True)
    registros_analizados: Mapped[int | None] = mapped_column(nullable=True)
    mismatch: Mapped[bool | None] = mapped_column(nullable=True, comment="true si top != actual")
    alerta_enviada: Mapped[bool] = mapped_column(nullable=False, default=False)
    creado_en: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)


class AuditoriaChangesTIModel(Base):
    """Auditoría de cambios en configuración de TI (Transformadores de Corriente)."""

    __tablename__ = "auditoria_cambios_ti"
    __table_args__ = (
        Index("idx_dispositivo_timestamp", "device_id", "timestamp"),
        Index("idx_tipo_cambio", "tipo_cambio"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    tipo_cambio: Mapped[str] = mapped_column(String(100), nullable=False)
    valor_anterior: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_nuevo: Mapped[str | None] = mapped_column(Text, nullable=True)
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    commit_git: Mapped[str | None] = mapped_column(String(40), nullable=True)
    usuario: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)

    device: Mapped["DeviceModel"] = relationship(back_populates="auditoria_cambios_ti")


class CambioContraseniaValidacionModel(Base):
    """Validación temporal de cambio de contraseña con OTP 4 dígitos (guardado como HMAC-SHA256)."""

    __tablename__ = "cambio_contrasena_validaciones"
    __table_args__ = (Index("idx_cambio_contrasena_validaciones_usuario_creado", "usuario_id", "creado_en"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    codigo_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    intentos_fallidos: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    ttl_expira: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    consumido_en: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    usuario: Mapped["UserModel"] = relationship()


class AuditoriaChangeContraseniaModel(Base):
    """Auditoría de cambios de contraseña."""

    __tablename__ = "auditoria_cambio_contrasena"
    __table_args__ = (Index("idx_auditoria_cambio_contrasena_usuario_creado", "usuario_id", "creado_en"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estado: Mapped[str] = mapped_column(String(50), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)

    usuario: Mapped["UserModel"] = relationship()


# Reexportación de modelos OAuth 2.0 PKCE para compatibilidad y registro en Base.metadata
from src.infrastructure.sqlalchemy.oauth_models import (  # noqa: E402, F401
    OAuthClientModel,
    OAuthCodeModel,
    OAuthRefreshTokenModel,
)

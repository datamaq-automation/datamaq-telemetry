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
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    plan_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pro_expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    free_tier_mode: Mapped[str] = mapped_column(String(30), default="PRIVADO_BASICO", nullable=False)
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
    unifilar_nodes: Mapped[list["FacilityUnifilarNodeModel"]] = relationship(
        back_populates="facility", cascade="all, delete-orphan"
    )
    zones: Mapped[list["FacilityZoneModel"]] = relationship(back_populates="facility", cascade="all, delete-orphan")
    device_layouts: Mapped[list["FacilityDeviceLayoutModel"]] = relationship(
        back_populates="facility", cascade="all, delete-orphan"
    )
    device_groups: Mapped[list["DeviceGroupModel"]] = relationship(
        back_populates="facility", cascade="all, delete-orphan"
    )


class FacilityUnifilarNodeModel(Base):
    __tablename__ = "unifilar_nodes"
    __table_args__ = (
        Index("idx_unifilar_facility", "facility_id"),
        Index("idx_unifilar_parent", "parent_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    facility_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    device_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    nominal_voltage_v: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    nominal_capacity_kva: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)

    facility: Mapped["FacilityModel"] = relationship(back_populates="unifilar_nodes")
    device: Mapped[Optional["DeviceModel"]] = relationship()


class DeviceGroupModel(Base):
    __tablename__ = "device_groups"
    __table_args__ = (Index("idx_device_group_facility", "facility_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    facility_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)

    facility: Mapped["FacilityModel"] = relationship(back_populates="device_groups")
    members: Mapped[list["DeviceGroupMemberModel"]] = relationship(back_populates="group", cascade="all, delete-orphan")


class DeviceGroupMemberModel(Base):
    __tablename__ = "device_group_members"

    group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("device_groups.id", ondelete="CASCADE"), primary_key=True
    )
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True)

    group: Mapped["DeviceGroupModel"] = relationship(back_populates="members")
    device: Mapped["DeviceModel"] = relationship()


class FacilityZoneModel(Base):
    __tablename__ = "facility_zones"
    __table_args__ = (Index("idx_zone_facility", "facility_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    facility_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    x_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    y_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    width_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    height_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)

    facility: Mapped["FacilityModel"] = relationship(back_populates="zones")


class FacilityDeviceLayoutModel(Base):
    __tablename__ = "facility_device_layouts"
    __table_args__ = (
        Index("idx_layout_facility", "facility_id"),
        Index("idx_layout_device", "device_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    facility_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    zone_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("facility_zones.id", ondelete="SET NULL"), nullable=True
    )
    pos_x_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    pos_y_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)

    facility: Mapped["FacilityModel"] = relationship(back_populates="device_layouts")
    device: Mapped["DeviceModel"] = relationship()
    zone: Mapped[Optional["FacilityZoneModel"]] = relationship()


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

    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)

    device: Mapped["DeviceModel"] = relationship(back_populates="instantaneous_readings")


class TelemetryEnergyModel(Base):
    __tablename__ = "telemetry_energy"
    __table_args__ = (
        Index("idx_telemetry_energy_dev_time", "device_id", "recorded_at"),
        Index("idx_telemetry_energy_time", "recorded_at"),
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
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)

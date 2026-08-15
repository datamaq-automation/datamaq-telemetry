import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
    tax_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)

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
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)

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

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

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

    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, nullable=False)

    device: Mapped["DeviceModel"] = relationship(back_populates="instantaneous_readings")


class TelemetryEnergyModel(Base):
    __tablename__ = "telemetry_energy"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    net_active_energy_kwh: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    net_reactive_energy_kvarh: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    imported_active_energy_kwh: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    exported_active_energy_kwh: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    imported_reactive_energy_kvarh: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    exported_reactive_energy_kvarh: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, nullable=False)

    device: Mapped["DeviceModel"] = relationship(back_populates="energy_readings")


class DeviceStatusLogModel(Base):
    __tablename__ = "device_status_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    wifi_rssi_dbm: Mapped[int | None] = mapped_column(nullable=True)
    wifi_calidad: Mapped[int | None] = mapped_column(nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, nullable=False)

    device: Mapped["DeviceModel"] = relationship(back_populates="status_logs")


class DeviceAlertModel(Base):
    __tablename__ = "device_alerts"

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
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    device: Mapped["DeviceModel"] = relationship(back_populates="alerts")


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)


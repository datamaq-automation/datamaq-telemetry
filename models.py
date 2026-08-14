import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Numeric,
    BigInteger,
    Integer,
    ForeignKey,
    Text,
    Enum,
    JSON,
)
from sqlalchemy.orm import relationship
from database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(150), nullable=False)
    tax_id = Column(String(50), nullable=True)
    contact_email = Column(String(120), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    facilities = relationship("Facility", back_populates="organization", cascade="all, delete-orphan")


class Facility(Base):
    __tablename__ = "facilities"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    address = Column(String(255), nullable=True)
    latitude = Column(Numeric(10, 8), nullable=True)
    longitude = Column(Numeric(11, 8), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    organization = relationship("Organization", back_populates="facilities")
    devices = relationship("Device", back_populates="facility")


class Device(Base):
    __tablename__ = "devices"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    facility_id = Column(String(36), ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True)
    device_uid = Column(String(64), unique=True, nullable=False, index=True)  # MAC address / Client ID
    serial_number = Column(String(64), nullable=True)
    name = Column(String(100), default="Nuevo Powermeter", nullable=False)
    model = Column(String(50), default="SmartPlus")
    hw_version = Column(String(50), nullable=True)
    fw_version = Column(String(50), nullable=True)
    tag_location = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    status = Column(String(20), default="OFFLINE", nullable=False)  # ONLINE, OFFLINE, WARNING
    last_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    facility = relationship("Facility", back_populates="devices")
    instantaneous_readings = relationship("TelemetryInstantaneous", back_populates="device", cascade="all, delete-orphan")
    energy_readings = relationship("TelemetryEnergy", back_populates="device", cascade="all, delete-orphan")
    status_logs = relationship("DeviceStatusLog", back_populates="device", cascade="all, delete-orphan")
    alerts = relationship("DeviceAlert", back_populates="device", cascade="all, delete-orphan")


class TelemetryInstantaneous(Base):
    __tablename__ = "telemetry_instantaneous"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    recorded_at = Column(DateTime, nullable=False, index=True)

    # Fase R
    voltage_r = Column(Numeric(6, 2), nullable=True)
    current_r = Column(Numeric(6, 2), nullable=True)
    active_power_r = Column(Numeric(10, 2), nullable=True)
    reactive_power_r = Column(Numeric(10, 2), nullable=True)
    apparent_power_r = Column(Numeric(10, 2), nullable=True)
    power_factor_r = Column(Numeric(4, 2), nullable=True)

    # Fase S
    voltage_s = Column(Numeric(6, 2), nullable=True)
    current_s = Column(Numeric(6, 2), nullable=True)
    active_power_s = Column(Numeric(10, 2), nullable=True)
    reactive_power_s = Column(Numeric(10, 2), nullable=True)
    apparent_power_s = Column(Numeric(10, 2), nullable=True)
    power_factor_s = Column(Numeric(4, 2), nullable=True)

    # Fase T
    voltage_t = Column(Numeric(6, 2), nullable=True)
    current_t = Column(Numeric(6, 2), nullable=True)
    active_power_t = Column(Numeric(10, 2), nullable=True)
    reactive_power_t = Column(Numeric(10, 2), nullable=True)
    apparent_power_t = Column(Numeric(10, 2), nullable=True)
    power_factor_t = Column(Numeric(4, 2), nullable=True)

    # Totales
    total_active_power = Column(Numeric(12, 2), nullable=True)
    total_reactive_power = Column(Numeric(12, 2), nullable=True)
    total_apparent_power = Column(Numeric(12, 2), nullable=True)
    total_power_factor = Column(Numeric(4, 2), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    device = relationship("Device", back_populates="instantaneous_readings")


class TelemetryEnergy(Base):
    __tablename__ = "telemetry_energy"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    recorded_at = Column(DateTime, nullable=False, index=True)

    net_active_energy_kwh = Column(Numeric(14, 3), nullable=True)
    net_reactive_energy_kvarh = Column(Numeric(14, 3), nullable=True)
    imported_active_energy_kwh = Column(Numeric(14, 3), nullable=True)
    exported_active_energy_kwh = Column(Numeric(14, 3), nullable=True)
    imported_reactive_energy_kvarh = Column(Numeric(14, 3), nullable=True)
    exported_reactive_energy_kvarh = Column(Numeric(14, 3), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    device = relationship("Device", back_populates="energy_readings")


class DeviceStatusLog(Base):
    __tablename__ = "device_status_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    recorded_at = Column(DateTime, nullable=False, index=True)
    wifi_rssi_dbm = Column(Integer, nullable=True)
    wifi_quality = Column(Integer, nullable=True)
    ip_address = Column(String(45), nullable=True)
    uptime_seconds = Column(BigInteger, nullable=True)
    raw_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    device = relationship("Device", back_populates="status_logs")


class DeviceAlert(Base):
    __tablename__ = "device_alerts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_type = Column(String(50), nullable=False)
    severity = Column(Enum("INFO", "WARNING", "CRITICAL", name="alert_severity"), default="WARNING", nullable=False)
    message = Column(Text, nullable=False)
    is_resolved = Column(Boolean, default=False, nullable=False)
    triggered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    device = relationship("Device", back_populates="alerts")

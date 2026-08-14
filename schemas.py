from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict


# Organization Schemas
class OrganizationBase(BaseModel):
    name: str
    tax_id: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationOut(OrganizationBase):
    id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# Facility Schemas
class FacilityBase(BaseModel):
    name: str
    organization_id: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class FacilityCreate(FacilityBase):
    pass


class FacilityOut(FacilityBase):
    id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# Device Schemas
class DeviceBase(BaseModel):
    device_uid: str
    serial_number: Optional[str] = None
    name: str = "Nuevo Powermeter"
    model: str = "SmartPlus"
    hw_version: Optional[str] = None
    fw_version: Optional[str] = None
    tag_location: Optional[str] = None
    is_active: bool = True
    facility_id: Optional[str] = None


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    facility_id: Optional[str] = None
    tag_location: Optional[str] = None
    is_active: Optional[bool] = None


class DeviceOut(DeviceBase):
    id: str
    status: str
    last_seen_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# Telemetry Instantaneous Schemas
class TelemetryInstantaneousOut(BaseModel):
    id: int
    device_id: str
    recorded_at: datetime
    voltage_r: Optional[float] = None
    current_r: Optional[float] = None
    active_power_r: Optional[float] = None
    reactive_power_r: Optional[float] = None
    apparent_power_r: Optional[float] = None
    power_factor_r: Optional[float] = None

    voltage_s: Optional[float] = None
    current_s: Optional[float] = None
    active_power_s: Optional[float] = None
    reactive_power_s: Optional[float] = None
    apparent_power_s: Optional[float] = None
    power_factor_s: Optional[float] = None

    voltage_t: Optional[float] = None
    current_t: Optional[float] = None
    active_power_t: Optional[float] = None
    reactive_power_t: Optional[float] = None
    apparent_power_t: Optional[float] = None
    power_factor_t: Optional[float] = None

    total_active_power: Optional[float] = None
    total_reactive_power: Optional[float] = None
    total_apparent_power: Optional[float] = None
    total_power_factor: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)


# Telemetry Energy Schemas
class TelemetryEnergyOut(BaseModel):
    id: int
    device_id: str
    recorded_at: datetime
    net_active_energy_kwh: Optional[float] = None
    net_reactive_energy_kvarh: Optional[float] = None
    imported_active_energy_kwh: Optional[float] = None
    exported_active_energy_kwh: Optional[float] = None
    imported_reactive_energy_kvarh: Optional[float] = None
    exported_reactive_energy_kvarh: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)


# Device Alert Schemas
class DeviceAlertOut(BaseModel):
    id: int
    device_id: str
    alert_type: str
    severity: str
    message: str
    is_resolved: bool
    triggered_at: datetime
    resolved_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

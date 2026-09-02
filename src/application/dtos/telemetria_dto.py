from typing import Any

from pydantic import BaseModel, ConfigDict

from src.application.dtos.tipos import FechaHoraUTC
from src.domain.telemetria.value_objects import EstadoFactorPotencia, EstadoTension


class MedicionFaseDTO(BaseModel):
    voltage_V: float | None = None
    current_A: float | None = None
    net_active_power_W: float | None = None
    net_reactive_power_VAR: float | None = None
    net_apparent_power_VA: float | None = None
    power_factor: float | None = None
    thd_v_pct: float | None = None
    thd_i_pct: float | None = None


class AnaliticaCalidadEnergiaDTO(BaseModel):
    requiere_compensacion: bool = False
    potencia_reactiva_a_compensar_kvar: float | None = None
    banco_sugerido_kvar: float | None = None
    penalizacion_estimada_ars: float | None = None
    desbalance_tension_porcentaje: float | None = None
    desbalance_corriente_porcentaje: float | None = None
    estado_fp: EstadoFactorPotencia = EstadoFactorPotencia.SIN_DATOS
    estado_tension: EstadoTension = EstadoTension.SIN_DATOS
    model_config = ConfigDict(from_attributes=True)


class LecturaInstantaneaDTO(BaseModel):
    id: int | None = None
    dispositivo_id: str
    registrado_en: FechaHoraUTC
    fase_r: MedicionFaseDTO
    fase_s: MedicionFaseDTO
    fase_t: MedicionFaseDTO
    potencia_activa_total_W: float | None = None
    potencia_reactiva_total_VAR: float | None = None
    potencia_aparente_total_VA: float | None = None
    factor_potencia_total: float | None = None
    desbalance_tension_porcentaje: float | None = None
    corriente_neutro_estimada_A: float | None = None
    voltage_linea_V: float | None = None
    tension_neutro_estimada_V: float | None = None
    thd_v_promedio_pct: float | None = None
    thd_i_total_pct: float | None = None
    analitica: AnaliticaCalidadEnergiaDTO | None = None
    model_config = ConfigDict(from_attributes=True)


class AcumuladoEnergiaDTO(BaseModel):
    id: int | None = None
    dispositivo_id: str
    registrado_en: FechaHoraUTC
    net_active_energy_kwh: float | None = None
    net_reactive_energy_kvarh: float | None = None
    imported_active_energy_kwh: float | None = None
    exported_active_energy_kwh: float | None = None
    imported_reactive_energy_kvarh: float | None = None
    exported_reactive_energy_kvarh: float | None = None
    model_config = ConfigDict(from_attributes=True)


class LogEstadoDispositivoDTO(BaseModel):
    id: int | None = None
    dispositivo_id: str
    registrado_en: FechaHoraUTC
    wifi_rssi_dbm: int | None = None
    wifi_calidad: int | None = None
    direccion_ip: str | None = None
    tiempo_activo_segundos: int | None = None
    payload_bruto: dict[str, Any] | None = None
    model_config = ConfigDict(from_attributes=True)


class TelemetriaLatestResponseDTO(BaseModel):
    device_id: str
    instantanea: LecturaInstantaneaDTO | None = None
    energia: AcumuladoEnergiaDTO | None = None
    analitica: AnaliticaCalidadEnergiaDTO | None = None

"""src/application/dtos/telemetria_dto.py."""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict

from src.application.dtos.tipos import FechaHoraUTC
from src.domain.telemetria.value_objects import (
    EstadoFactorPotencia,
    EstadoMetrologicoLectura,
    EstadoTension,
)


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
    recargo_porcentaje: float | None = 0.0
    motivo_abstencion: str | None = None
    ventana_evaluacion_min: int | None = 15
    vigente_desde: FechaHoraUTC | None = None
    factor_potencia_integrado: float | None = None
    model_config = ConfigDict(from_attributes=True)


class DiagnosticoInstalacionDTO(BaseModel):
    estado_metrologico: EstadoMetrologicoLectura = EstadoMetrologicoLectura.CONFIABLE
    fases_validas: list[str] = ["R", "S", "T"]
    fases_comprometidas: list[str] = []
    anomalias_detectadas: list[str] = []
    potencia_estimada_simetrica_w: float | None = None
    accion_correctiva_sugerida: str | None = None
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
    diagnostico_instalacion: DiagnosticoInstalacionDTO | None = None
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


class EnergiaAgregadaDTO(BaseModel):
    periodo: date
    energia_activa_neta_kwh: float | None = None
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


class DiagnosticoFaseDTO(BaseModel):
    fp_original: float | None = None
    angulo_phi_grados: float | None = None
    potencia_activa_w: float | None = None
    potencia_reactiva_var: float | None = None
    rotacion_optima_sugerida: str | None = None
    fp_con_rotacion_optima: float | None = None
    potencia_activa_con_rotacion_optima_w: float | None = None
    potencia_reactiva_con_rotacion_optima_var: float | None = None
    rotaciones_evaluadas: dict[str, dict[str, float]] | None = None
    tension_v: float | None = None
    corriente_a: float | None = None
    factor_potencia: float | None = None
    angulo_fasorial_grados: float | None = None
    tc_invertido_180: bool = False
    estado_ti: str = "CORRECTO"
    duplicado_con_fase: str | None = None
    validez_metrologica: bool = True


class DiagnosticoFasesDispositivoDTO(BaseModel):
    dispositivo_id: str
    evaluado_en: FechaHoraUTC
    fase_r: DiagnosticoFaseDTO
    fase_s: DiagnosticoFaseDTO
    fase_t: DiagnosticoFaseDTO
    diagnostico_general: str
    recomendacion_hardware: str
    fases: dict[str, DiagnosticoFaseDTO] | None = None
    secuencia_fases: str = "DIRECTA"
    rotacion_correcta: bool = True
    alertas_fasoriales: list[str] = []

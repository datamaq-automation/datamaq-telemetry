"""src/infrastructure/sqlalchemy/repositories/telemetria_mappers.py."""

from decimal import Decimal

from src.domain.telemetria.entities import (
    AcumuladoEnergia,
    AlertaDispositivo,
    LecturaInstantanea,
    MedicionFase,
)
from src.domain.telemetria.value_objects import (
    Corriente,
    EnergiaActiva,
    EnergiaReactiva,
    FactorPotencia,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    SeveridadAlerta,
    Tension,
)
from src.infrastructure.sqlalchemy.models import (
    DeviceAlertModel,
    TelemetryEnergyModel,
    TelemetryInstantaneousModel,
)


def to_fase(v, i, p, q, s, fp, thd_v=None, thd_i=None) -> MedicionFase:
    return MedicionFase(
        tension=Tension(voltios=float(v)) if v is not None else None,
        corriente=Corriente(amperios=float(i)) if i is not None else None,
        potencia_activa=PotenciaActiva(vatios=float(p)) if p is not None else None,
        potencia_reactiva=PotenciaReactiva(var=float(q)) if q is not None else None,
        potencia_aparente=PotenciaAparente(va=float(s)) if s is not None else None,
        factor_potencia=FactorPotencia(valor=float(fp)) if fp is not None else None,
        thd_v_porcentaje=float(thd_v) if thd_v is not None else None,
        thd_i_porcentaje=float(thd_i) if thd_i is not None else None,
    )


def _extraer_fases_instantanea(m: TelemetryInstantaneousModel) -> tuple[MedicionFase, MedicionFase, MedicionFase]:
    fase_r = to_fase(
        m.voltage_r,
        m.current_r,
        m.active_power_r,
        m.reactive_power_r,
        m.apparent_power_r,
        m.power_factor_r,
        getattr(m, "thd_v_r", None),
        getattr(m, "thd_i_r", None),
    )
    fase_s = to_fase(
        m.voltage_s,
        m.current_s,
        m.active_power_s,
        m.reactive_power_s,
        m.apparent_power_s,
        m.power_factor_s,
        getattr(m, "thd_v_s", None),
        getattr(m, "thd_i_s", None),
    )
    fase_t = to_fase(
        m.voltage_t,
        m.current_t,
        m.active_power_t,
        m.reactive_power_t,
        m.apparent_power_t,
        m.power_factor_t,
        getattr(m, "thd_v_t", None),
        getattr(m, "thd_i_t", None),
    )
    return fase_r, fase_s, fase_t


def instantanea_to_entity(m: TelemetryInstantaneousModel) -> LecturaInstantanea:
    fase_r, fase_s, fase_t = _extraer_fases_instantanea(m)

    in_obj = None
    if hasattr(m, "current_n") and m.current_n is not None:
        in_obj = Corriente(amperios=float(m.current_n))

    vl_val = float(m.voltage_linea_V) if hasattr(m, "voltage_linea_V") and m.voltage_linea_V is not None else None
    vn_val = (
        float(m.tension_neutro_estimada)
        if hasattr(m, "tension_neutro_estimada") and m.tension_neutro_estimada is not None
        else None
    )
    thd_v_prom_val = (
        float(m.thd_v_promedio_porcentaje)
        if hasattr(m, "thd_v_promedio_porcentaje") and m.thd_v_promedio_porcentaje is not None
        else None
    )
    thd_i_tot_val = (
        float(m.thd_i_total_porcentaje)
        if hasattr(m, "thd_i_total_porcentaje") and m.thd_i_total_porcentaje is not None
        else None
    )

    return LecturaInstantanea(
        id=m.id,
        dispositivo_id=m.device_id,
        registrado_en=m.recorded_at,
        fase_r=fase_r,
        fase_s=fase_s,
        fase_t=fase_t,
        potencia_activa_total=PotenciaActiva(vatios=float(m.total_active_power))
        if m.total_active_power is not None
        else None,
        potencia_reactiva_total=PotenciaReactiva(var=float(m.total_reactive_power))
        if m.total_reactive_power is not None
        else None,
        potencia_aparente_total=PotenciaAparente(va=float(m.total_apparent_power))
        if m.total_apparent_power is not None
        else None,
        factor_potencia_total=FactorPotencia(valor=float(m.total_power_factor))
        if m.total_power_factor is not None
        else None,
        desbalance_tension_porcentaje=float(m.desbalance_tension_porcentaje)
        if m.desbalance_tension_porcentaje is not None
        else None,
        corriente_neutro_estimada=in_obj,
        voltage_linea_V=vl_val,
        tension_neutro_estimada=vn_val,
        thd_v_promedio_porcentaje=thd_v_prom_val,
        thd_i_total_porcentaje=thd_i_tot_val,
    )


def energia_to_entity(m: TelemetryEnergyModel) -> AcumuladoEnergia:
    return AcumuladoEnergia(
        id=m.id,
        dispositivo_id=m.device_id,
        registrado_en=m.recorded_at,
        energia_activa_neta=EnergiaActiva(kwh=float(m.net_active_energy_kwh))
        if m.net_active_energy_kwh is not None
        else None,
        energia_reactiva_neta=EnergiaReactiva(kvarh=float(m.net_reactive_energy_kvarh))
        if m.net_reactive_energy_kvarh is not None
        else None,
        energia_activa_importada=EnergiaActiva(kwh=float(m.imported_active_energy_kwh))
        if m.imported_active_energy_kwh is not None
        else None,
        energia_activa_exportada=EnergiaActiva(kwh=float(m.exported_active_energy_kwh))
        if m.exported_active_energy_kwh is not None
        else None,
        energia_reactiva_importada=EnergiaReactiva(kvarh=float(m.imported_reactive_energy_kvarh))
        if m.imported_reactive_energy_kvarh is not None
        else None,
        fuente=m.source,
        energia_reactiva_exportada=EnergiaReactiva(kvarh=float(m.exported_reactive_energy_kvarh))
        if m.exported_reactive_energy_kvarh is not None
        else None,
    )


def alerta_to_entity(m: DeviceAlertModel) -> AlertaDispositivo:
    return AlertaDispositivo(
        id=m.id,
        dispositivo_id=m.device_id,
        tipo_alerta=m.alert_type,
        severidad=SeveridadAlerta(m.severity)
        if m.severity in SeveridadAlerta._value2member_map_
        else SeveridadAlerta.WARNING,
        mensaje=m.message,
        esta_resuelta=m.is_resolved,
        disparada_en=m.triggered_at,
        resuelta_en=m.resolved_at,
        fase=m.phase,
        valor_medido=float(m.measured_value) if m.measured_value is not None else None,
        valor_umbral=float(m.threshold_value) if m.threshold_value is not None else None,
        unidad=m.unit,
        categoria=m.category,
        observaciones=m.notes,
        ultima_deteccion_en=m.last_detected_at,
        ocurrencias=m.occurrences or 1,
    )


def alerta_a_modelo(alerta: AlertaDispositivo, model: DeviceAlertModel) -> DeviceAlertModel:
    """Copia la alerta al modelo (alta o actualización): un solo lugar para los dos caminos de guardar_alerta."""
    model.device_id = alerta.dispositivo_id
    model.alert_type = alerta.tipo_alerta
    model.severity = alerta.severidad.value
    model.message = alerta.mensaje
    model.is_resolved = alerta.esta_resuelta
    model.triggered_at = alerta.disparada_en
    model.resolved_at = alerta.resuelta_en
    model.phase = alerta.fase
    model.measured_value = Decimal(str(alerta.valor_medido)) if alerta.valor_medido is not None else None
    model.threshold_value = Decimal(str(alerta.valor_umbral)) if alerta.valor_umbral is not None else None
    model.unit = alerta.unidad
    model.category = alerta.categoria
    model.notes = alerta.observaciones
    model.last_detected_at = alerta.ultima_deteccion_en
    model.occurrences = alerta.ocurrencias
    return model

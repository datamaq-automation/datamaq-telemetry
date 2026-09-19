# src/application/mappers/payload_helpers.py
"""Helpers for power/THD extraction used by payload parsers."""

from typing import Any

# acotar_payload_bruto no se usa aquí; import eliminado para pasar ruff
from src.domain.telemetria.entities import MedicionFase
from src.domain.telemetria.services import CalculadoraPotenciaService


def _extraer_potencia_activa_total(
    total_data: dict[str, Any],
    fase_r: MedicionFase,
    fase_s: MedicionFase,
    fase_t: MedicionFase,
    has_phases_dict: bool,
) -> float | None:
    p_tot = (
        total_data.get("net_active_power_W")
        or total_data.get("m_p_tot")
        or total_data.get("total_active_power")
        or total_data.get("p_tot")
        or total_data.get("P_tot")
    )
    if p_tot is None and not has_phases_dict:
        p_tot = total_data.get("p")
    if p_tot is None:
        p_vals = [f.potencia_activa.vatios for f in (fase_r, fase_s, fase_t) if f.potencia_activa is not None]
        if p_vals:
            p_tot = sum(p_vals)
    return float(p_tot) if p_tot is not None else None


def _extraer_potencia_reactiva_total(
    total_data: dict[str, Any],
    fase_r: MedicionFase,
    fase_s: MedicionFase,
    fase_t: MedicionFase,
    has_phases_dict: bool,
) -> float | None:
    q_tot = (
        total_data.get("net_reactive_power_VAR")
        or total_data.get("m_q_tot")
        or total_data.get("total_reactive_power")
        or total_data.get("q_tot")
        or total_data.get("Q_tot")
    )
    if q_tot is None and not has_phases_dict:
        q_tot = total_data.get("q")
    if q_tot is None:
        q_vals = [f.potencia_reactiva.var for f in (fase_r, fase_s, fase_t) if f.potencia_reactiva is not None]
        if q_vals:
            q_tot = sum(q_vals)
    return float(q_tot) if q_tot is not None else None


def _extraer_potencia_aparente_total(
    total_data: dict[str, Any],
    fase_r: MedicionFase,
    fase_s: MedicionFase,
    fase_t: MedicionFase,
    has_phases_dict: bool,
) -> float | None:
    s_tot = (
        total_data.get("net_apparent_power_VA")
        or total_data.get("m_s_tot")
        or total_data.get("total_apparent_power")
        or total_data.get("s_tot")
        or total_data.get("S_tot")
    )
    if s_tot is None and not has_phases_dict:
        s_tot = total_data.get("s")
    if s_tot is None:
        s_tot = CalculadoraPotenciaService.calcular_potencia_aparente_total(
            *(f.potencia_aparente.va if f.potencia_aparente is not None else None for f in (fase_r, fase_s, fase_t))
        )
    return float(s_tot) if s_tot is not None else None


def _extraer_fp_total(
    total_data: dict[str, Any],
    p_tot: float | None,
    s_tot: float | None,
    has_phases_dict: bool,
) -> float | None:
    fp_tot = (
        total_data.get("power_factor")
        or total_data.get("m_pf_tot")
        or total_data.get("total_power_factor")
        or total_data.get("fp_tot")
        or total_data.get("pf_tot")
    )
    if fp_tot is None and not has_phases_dict:
        fp_tot = total_data.get("fp") or total_data.get("pf")
    if fp_tot is None:
        fp_tot = CalculadoraPotenciaService.calcular_factor_potencia(
            float(p_tot) if p_tot is not None else None,
            float(s_tot) if s_tot is not None else None,
        )
    return float(fp_tot) if fp_tot is not None else None


def _calcular_totales_potencia(
    total_data: dict[str, Any],
    fase_r: MedicionFase,
    fase_s: MedicionFase,
    fase_t: MedicionFase,
    has_phases_dict: bool,
) -> tuple[float | None, float | None, float | None, float | None]:
    p_tot = _extraer_potencia_activa_total(total_data, fase_r, fase_s, fase_t, has_phases_dict)
    q_tot = _extraer_potencia_reactiva_total(total_data, fase_r, fase_s, fase_t, has_phases_dict)
    s_tot = _extraer_potencia_aparente_total(total_data, fase_r, fase_s, fase_t, has_phases_dict)
    fp_tot = _extraer_fp_total(total_data, p_tot, s_tot, has_phases_dict)
    return p_tot, q_tot, s_tot, fp_tot


def _calcular_totales_thd(
    total_data: dict[str, Any],
    payload: dict[str, Any],
    fase_r: MedicionFase,
    fase_s: MedicionFase,
    fase_t: MedicionFase,
) -> tuple[float | None, float | None]:
    thd_v_prom = (
        total_data.get("thd_v_promedio_pct")
        or total_data.get("thd_v_promedio")
        or total_data.get("thd_v_avg")
        or total_data.get("thdv_avg")
        or payload.get("thd_v_promedio_pct")
        or payload.get("thd_v_avg")
    )
    if thd_v_prom is None:
        thd_v_vals = [f.thd_v_porcentaje for f in (fase_r, fase_s, fase_t) if f.thd_v_porcentaje is not None]
        if thd_v_vals:
            thd_v_prom = sum(thd_v_vals) / len(thd_v_vals)

    thd_i_tot = (
        total_data.get("thd_i_total_pct")
        or total_data.get("thd_i_total")
        or total_data.get("thd_i_tot")
        or total_data.get("thdi_tot")
        or payload.get("thd_i_total_pct")
        or payload.get("thd_i_tot")
    )
    if thd_i_tot is None:
        thd_i_vals = [f.thd_i_porcentaje for f in (fase_r, fase_s, fase_t) if f.thd_i_porcentaje is not None]
        if thd_i_vals:
            thd_i_tot = sum(thd_i_vals) / len(thd_i_vals)

    return (
        round(float(thd_v_prom), 2) if thd_v_prom is not None else None,
        round(float(thd_i_tot), 2) if thd_i_tot is not None else None,
    )

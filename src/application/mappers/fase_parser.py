"""src/application/mappers/fase_parser.py."""

import ipaddress
from datetime import datetime, timezone
from typing import Any

from src.domain.telemetria.entities import MedicionFase
from src.domain.telemetria.services import CalculadoraPotenciaService
from src.domain.telemetria.value_objects import (
    Corriente,
    FactorPotencia,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    Tension,
)

_METRICA_ALIASES: dict[str, list[str]] = {
    "v": ["voltage_V", "m_v", "voltage", "v", "V"],
    "i": ["current_A", "m_i", "current", "i", "I"],
    "p": ["net_active_power_W", "m_p", "active_power", "p", "P"],
    "q": ["net_reactive_power_VAR", "m_q", "reactive_power", "q", "Q"],
    "s": ["net_apparent_power_VA", "m_s", "apparent_power", "s", "S"],
    "fp": ["power_factor", "m_pf", "pf", "fp"],
    "thd_v": ["thd_v_pct", "thd_v", "thd_v_porcentaje", "thdv", "tv"],
    "thd_i": ["thd_i_pct", "thd_i", "thd_i_porcentaje", "thdi", "ti"],
}


def parse_timestamp(ts_val: Any) -> datetime:
    """Parsea un timestamp en formato numérico epoch o cadena ISO 8601 a UTC."""
    if ts_val:
        try:
            if isinstance(ts_val, (int, float)) and ts_val > 1000000000:
                return datetime.fromtimestamp(ts_val, tz=timezone.utc)
            elif isinstance(ts_val, str):
                return datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
        except Exception:
            pass
    return datetime.now(timezone.utc)


def sanear_entero(valor: Any) -> int | None:
    """Convierte un valor a entero; retorna None si no es un número entero válido."""
    if isinstance(valor, bool):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def sanear_ip(valor: Any) -> str | None:
    """Valida y normaliza una dirección IP; retorna None si es inválida."""
    if not isinstance(valor, str):
        return None
    try:
        return str(ipaddress.ip_address(valor))
    except ValueError:
        return None


def acotar_payload_bruto(payload: dict[str, Any]) -> dict[str, Any]:
    """Reduce el payload bruto persistido a los campos de interés conocidos."""
    wifi = payload.get("wifi_sta")
    device = payload.get("device_info")
    return {
        "wifi_sta": wifi if isinstance(wifi, dict) else {},
        "device_info": device if isinstance(device, dict) else {},
    }


def _extraer_metrica(data: dict[str, Any], metrica: str, suffix: str = "") -> Any:
    sfx_lower = suffix.lower()
    sfx_upper = suffix.upper()
    sfx_clean = suffix.replace("_", "")
    prefixes = [suffix, sfx_lower, sfx_upper, sfx_clean, sfx_clean.upper()]

    aliases = _METRICA_ALIASES.get(metrica, [])
    for pfx in prefixes:
        for alias in aliases:
            key = f"{alias}{pfx}"
            if key in data and data[key] is not None:
                return data[key]
    for alias in aliases:
        if alias in data and data[alias] is not None:
            return data[alias]
    return None


def invertir_fase_ct(fase: MedicionFase) -> MedicionFase:
    """Corrige una fase cuyo TI está clampeado al revés (180° de fase).

    Un TI invertido reporta P y Q con signo opuesto al real; V, I y S no
    dependen del sentido del TI y quedan sin cambios.
    """
    p = fase.potencia_activa
    q = fase.potencia_reactiva
    fp = fase.factor_potencia
    return MedicionFase(
        tension=fase.tension,
        corriente=fase.corriente,
        potencia_activa=PotenciaActiva(vatios=-p.vatios) if p is not None else None,
        potencia_reactiva=PotenciaReactiva(var=-q.var) if q is not None else None,
        potencia_aparente=fase.potencia_aparente,
        factor_potencia=FactorPotencia(valor=-fp.valor) if fp is not None else None,
        thd_v_porcentaje=fase.thd_v_porcentaje,
        thd_i_porcentaje=fase.thd_i_porcentaje,
    )


def parse_fase(data: Any, suffix: str = "") -> MedicionFase:
    """Parsea mediciones de una fase individual soportando múltiples convenciones de firmware."""
    if not isinstance(data, dict):
        return MedicionFase()

    v = _extraer_metrica(data, "v", suffix)
    i = _extraer_metrica(data, "i", suffix)
    p = _extraer_metrica(data, "p", suffix)
    q = _extraer_metrica(data, "q", suffix)
    s = _extraer_metrica(data, "s", suffix)
    fp = _extraer_metrica(data, "fp", suffix)
    thd_v = _extraer_metrica(data, "thd_v", suffix)
    thd_i = _extraer_metrica(data, "thd_i", suffix)

    s_calc = CalculadoraPotenciaService.calcular_potencia_aparente(
        float(v) if v is not None else None,
        float(i) if i is not None else None,
    )
    s_final = s_calc if s_calc is not None else (float(s) if s is not None else None)
    fp_calc = CalculadoraPotenciaService.calcular_factor_potencia(float(p) if p is not None else None, s_final)
    fp_final = fp_calc if fp_calc is not None else (float(fp) if fp is not None else None)

    return MedicionFase(
        tension=Tension(voltios=float(v)) if v is not None else None,
        corriente=Corriente(amperios=float(i)) if i is not None else None,
        potencia_activa=PotenciaActiva(vatios=float(p)) if p is not None else None,
        potencia_reactiva=PotenciaReactiva(var=float(q)) if q is not None else None,
        potencia_aparente=PotenciaAparente(va=s_final) if s_final is not None else None,
        factor_potencia=FactorPotencia(valor=fp_final) if fp_final is not None else None,
        thd_v_porcentaje=float(thd_v) if thd_v is not None else None,
        thd_i_porcentaje=float(thd_i) if thd_i is not None else None,
    )

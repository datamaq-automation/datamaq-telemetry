"""src/application/mappers/energia_parser.py."""

import math
from datetime import datetime
from typing import Any

from src.domain.telemetria.entities import AcumuladoEnergia
from src.domain.telemetria.value_objects import EnergiaActiva, EnergiaReactiva


def _parse_angulos_map(correccion_angular: str | dict[str, float] | None) -> dict[str, float]:
    if isinstance(correccion_angular, dict):
        return {k.upper(): float(v) for k, v in correccion_angular.items()}
    if isinstance(correccion_angular, str) and correccion_angular:
        angulos_map: dict[str, float] = {}
        for item in correccion_angular.split(","):
            if ":" in item:
                k, v = item.split(":", 1)
                try:
                    angulos_map[k.strip().upper()] = float(v.strip())
                except ValueError:
                    pass
        return angulos_map
    return {}


def _procesar_fases_acumuladas(
    fases_items: list[Any],
    fases_con_ti: set[str] | None,
    angulos_map: dict[str, float],
) -> tuple[list[float], list[float]]:
    if fases_con_ti is not None:
        fases_items = [
            item
            for item in fases_items
            if isinstance(item, dict) and str(item.get("n", "")).strip().upper() in fases_con_ti
        ]
    phases_act, phases_react = [], []
    for item in fases_items:
        if not isinstance(item, dict):
            continue
        n_fase = str(item.get("n", "")).strip().upper()
        a_val = float(item["a"]) if item.get("a") is not None else None
        r_val = float(item["r"]) if item.get("r") is not None else None

        if (a_val is not None or r_val is not None) and n_fase in angulos_map:
            alpha = angulos_map[n_fase]
            rad = math.radians(alpha)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            a_prim = (a_val or 0.0) * cos_a + (r_val or 0.0) * sin_a
            r_prim = (r_val or 0.0) * cos_a - (a_val or 0.0) * sin_a
            if a_val is not None:
                phases_act.append(a_prim)
            if r_val is not None:
                phases_react.append(r_prim)
        else:
            if a_val is not None:
                phases_act.append(a_val)
            if r_val is not None:
                phases_react.append(r_val)
    return phases_act, phases_react


class EnergiaPayloadParser:
    """Parsea acumulados y totales de energía activa y reactiva desde payloads MQTT."""

    @classmethod
    def _extraer_energias_totales(
        cls, total: dict[str, Any]
    ) -> tuple[float | None, float | None, float | None, float | None, float | None, float | None]:
        e_act_imp = (
            total.get("imported_active_energy_KWH")
            or total.get("ae_imp")
            or total.get("ae_imported")
            or total.get("m_ae_imp")
        )
        e_act_exp = (
            total.get("exported_active_energy_KWH")
            or total.get("ae_exp")
            or total.get("ae_exported")
            or total.get("m_ae_exp")
        )
        e_react_imp = (
            total.get("imported_reactive_energy_KVARH")
            or total.get("re_imp")
            or total.get("re_imported")
            or total.get("m_re_imp")
        )
        e_react_exp = (
            total.get("exported_reactive_energy_KVARH")
            or total.get("re_exp")
            or total.get("re_exported")
            or total.get("m_re_exp")
        )
        e_act = (
            total.get("net_active_energy_KWH")
            or total.get("ae_net")
            or total.get("ae_tot")
            or (
                (float(e_act_imp) - float(e_act_exp))
                if e_act_imp is not None and e_act_exp is not None
                else (float(e_act_imp) if e_act_imp is not None else None)
            )
        )
        e_react = (
            total.get("net_reactive_energy_KVARH")
            or total.get("re_net")
            or total.get("re_tot")
            or (
                (float(e_react_imp) - float(e_react_exp))
                if e_react_imp is not None and e_react_exp is not None
                else (float(e_react_imp) if e_react_imp is not None else None)
            )
        )
        return (
            float(e_act) if e_act is not None else None,
            float(e_react) if e_react is not None else None,
            float(e_act_imp) if e_act_imp is not None else None,
            float(e_act_exp) if e_act_exp is not None else None,
            float(e_react_imp) if e_react_imp is not None else None,
            float(e_react_exp) if e_react_exp is not None else None,
        )

    @classmethod
    def parsear_acumulado(
        cls,
        payload: dict[str, Any],
        dispositivo_id: str,
        recorded_at: datetime,
        fases_con_ti: set[str] | None = None,
        fuente: str | None = None,
        correccion_angular: str | dict[str, float] | None = None,
    ) -> AcumuladoEnergia:
        """``fases_con_ti`` filtra qué fases suma el array ``f`` de ``acc`` (solo aplica
        a ese formato: ``energyio`` ya llega como total del equipo, sin desglose por
        fase). Sin ``fases_con_ti`` se suman todas las fases presentes, como antes.

        ``fuente`` identifica el subtópico de origen ("acc" / "energyio") para que
        el repositorio decida qué serie prioriza al persistir (D1: energyio manda).

        ``correccion_angular`` aplica la rotación trigonométrica fasorial a la energía de cada fase.
        """
        total = payload.get("total") if isinstance(payload.get("total"), dict) else payload
        total_dict = total if isinstance(total, dict) else {}

        e_act, e_react, e_act_imp, e_act_exp, e_react_imp, e_react_exp = cls._extraer_energias_totales(total_dict)
        angulos_map = _parse_angulos_map(correccion_angular)

        if isinstance(payload.get("f"), list):
            phases_act, phases_react = _procesar_fases_acumuladas(payload["f"], fases_con_ti, angulos_map)
            if phases_act:
                e_act = sum(phases_act)
                if e_act_imp is None:
                    e_act_imp = e_act
            if phases_react:
                e_react = sum(phases_react)
                if e_react_imp is None:
                    e_react_imp = e_react

        return AcumuladoEnergia(
            id=None,
            dispositivo_id=dispositivo_id,
            registrado_en=recorded_at,
            energia_activa_neta=EnergiaActiva(kwh=e_act) if e_act is not None else None,
            energia_reactiva_neta=EnergiaReactiva(kvarh=e_react) if e_react is not None else None,
            energia_activa_importada=EnergiaActiva(kwh=e_act_imp) if e_act_imp is not None else None,
            energia_activa_exportada=EnergiaActiva(kwh=e_act_exp) if e_act_exp is not None else None,
            energia_reactiva_importada=EnergiaReactiva(kvarh=e_react_imp) if e_react_imp is not None else None,
            energia_reactiva_exportada=EnergiaReactiva(kvarh=e_react_exp) if e_react_exp is not None else None,
            fuente=fuente,
        )

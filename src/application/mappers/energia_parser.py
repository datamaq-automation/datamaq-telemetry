"""src/application/mappers/energia_parser.py."""
from datetime import datetime
from typing import Any

from src.domain.telemetria.entities import AcumuladoEnergia
from src.domain.telemetria.value_objects import EnergiaActiva, EnergiaReactiva


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
    ) -> AcumuladoEnergia:
        total = payload.get("total") if isinstance(payload.get("total"), dict) else payload
        total_dict = total if isinstance(total, dict) else {}

        e_act, e_react, e_act_imp, e_act_exp, e_react_imp, e_react_exp = cls._extraer_energias_totales(total_dict)

        if isinstance(payload.get("f"), list):
            phases_act = [
                float(item["a"]) for item in payload["f"] if isinstance(item, dict) and item.get("a") is not None
            ]
            phases_react = [
                float(item["r"]) for item in payload["f"] if isinstance(item, dict) and item.get("r") is not None
            ]
            if e_act is None and phases_act:
                e_act = sum(phases_act)
                if e_act_imp is None:
                    e_act_imp = e_act
            if e_react is None and phases_react:
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
        )

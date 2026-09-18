"""src/application/mappers/payload_telemetria_parser.py."""

from dataclasses import replace
from datetime import datetime
from typing import Any

from src.application.mappers.energia_parser import EnergiaPayloadParser
from src.application.mappers.fase_parser import (
    acotar_payload_bruto,
    aplicar_configuracion_ti,
    invertir_fase_ct,
    parse_fase,
    parse_timestamp,
    rotar_fase_fasorial,
    sanear_entero,
    sanear_ip,
)
from src.application.mappers.payload_helpers import _calcular_totales_potencia, _calcular_totales_thd
from src.domain.telemetria.entities import (
    AcumuladoEnergia,
    AlertaDispositivo,
    Dispositivo,
    LecturaInstantanea,
    LogEstadoDispositivo,
    MedicionFase,
)
from src.domain.telemetria.services import (
    AnalizadorCalidadEnergiaService,
    CalculadoraPotenciaService,
)
from src.domain.telemetria.servicios.evaluador_diagnostico_instalacion import (
    EvaluadorDiagnosticoInstalacionService,
)
from src.domain.telemetria.value_objects import (
    Corriente,
    FactorPotencia,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    SeveridadAlerta,
)


def _calcular_derivadas_red(
    fase_r: MedicionFase,
    fase_s: MedicionFase,
    fase_t: MedicionFase,
    es_monofasico: bool,
) -> tuple[float | None, float | None, Corriente | None, float | None]:
    vr = fase_r.tension.voltios if fase_r.tension else None
    vs = fase_s.tension.voltios if fase_s.tension else None
    vt = fase_t.tension.voltios if fase_t.tension else None
    desbalance_v = AnalizadorCalidadEnergiaService.calcular_desbalance_tension(vr, vs, vt)

    tensiones_fase = [v for v in (vr, vs, vt) if v is not None]
    voltage_linea_V = None
    if tensiones_fase:
        promedio_fase = sum(tensiones_fase) / len(tensiones_fase)
        voltage_linea_V = round(promedio_fase * 1.7320508075688772, 2)

    ir_val = fase_r.corriente.amperios if fase_r.corriente else None
    is_val = fase_s.corriente.amperios if fase_s.corriente else None
    it_val = fase_t.corriente.amperios if fase_t.corriente else None
    pr_val = fase_r.potencia_activa.vatios if fase_r.potencia_activa else None
    ps_val = fase_s.potencia_activa.vatios if fase_s.potencia_activa else None
    pt_val = fase_t.potencia_activa.vatios if fase_t.potencia_activa else None
    qr_val = fase_r.potencia_reactiva.var if fase_r.potencia_reactiva else None
    qs_val = fase_s.potencia_reactiva.var if fase_s.potencia_reactiva else None
    qt_val = fase_t.potencia_reactiva.var if fase_t.potencia_reactiva else None

    i_neutro = AnalizadorCalidadEnergiaService.calcular_corriente_neutro(
        ir_val, is_val, it_val, pr_val, ps_val, pt_val, qr_val, qs_val, qt_val
    )
    v_neutro = AnalizadorCalidadEnergiaService.calcular_tension_neutro(
        vr, vs, vt, ir_val, is_val, it_val, pr_val, ps_val, pt_val, qr_val, qs_val, qt_val
    )

    if es_monofasico:
        return None, None, None, None

    return desbalance_v, voltage_linea_V, i_neutro, v_neutro


def _aplicar_fases_invertidas(
    fase_r: MedicionFase, fase_s: MedicionFase, fase_t: MedicionFase, dispositivo: Dispositivo
) -> tuple[MedicionFase, MedicionFase, MedicionFase]:
    fases_invertidas = {
        f.strip().upper() for f in (getattr(dispositivo, "ct_fases_invertidas", "") or "").split(",") if f.strip()
    }
    if "R" in fases_invertidas:
        fase_r = invertir_fase_ct(fase_r)
    if "S" in fases_invertidas:
        fase_s = invertir_fase_ct(fase_s)
    if "T" in fases_invertidas:
        fase_t = invertir_fase_ct(fase_t)
    return fase_r, fase_s, fase_t


def _aplicar_rotacion_angulos(
    fase_r: MedicionFase, fase_s: MedicionFase, fase_t: MedicionFase, dispositivo: Dispositivo
) -> tuple[MedicionFase, MedicionFase, MedicionFase]:
    angulos_raw = getattr(dispositivo, "correccion_angular_fases", "") or ""
    angulos_map: dict[str, float] = {}
    if angulos_raw:
        for item in str(angulos_raw).split(","):
            if ":" in item:
                k, v = item.split(":", 1)
                try:
                    angulos_map[k.strip().upper()] = float(v.strip())
                except ValueError:
                    pass
    if "R" in angulos_map:
        fase_r = rotar_fase_fasorial(fase_r, angulos_map["R"])
    if "S" in angulos_map:
        fase_s = rotar_fase_fasorial(fase_s, angulos_map["S"])
    if "T" in angulos_map:
        fase_t = rotar_fase_fasorial(fase_t, angulos_map["T"])
    return fase_r, fase_s, fase_t


class TelemetriaPayloadParser:
    """Transforma payloads heterogéneos de firmware MQTT a entidades de dominio."""

    @staticmethod
    def parse_timestamp(ts_val: Any) -> datetime:
        return parse_timestamp(ts_val)

    @staticmethod
    def parse_fase(data: Any, suffix: str = "") -> MedicionFase:
        return parse_fase(data, suffix=suffix)

    @classmethod
    def _extraer_dict_fases(
        cls, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], bool]:
        phases_dict: dict[str, dict[str, Any]] = {}
        if isinstance(payload.get("f"), list):
            for item in payload["f"]:
                if isinstance(item, dict) and "n" in item:
                    phases_dict[str(item["n"]).strip().upper()] = item

        root_n = payload.get("n")
        if isinstance(root_n, str) and root_n.strip():
            fase_raiz = root_n.strip().upper()
            return (
                payload if fase_raiz == "R" else {},
                payload if fase_raiz == "S" else {},
                payload if fase_raiz == "T" else {},
                bool(phases_dict),
            )

        data_r = (
            phases_dict.get("R")
            or phases_dict.get("1")
            or payload.get("phase_r")
            or payload.get("phase_1")
            or payload.get("fase_r")
            or (payload.get("r") if isinstance(payload.get("r"), dict) else None)
            or payload
        )
        data_s = (
            phases_dict.get("S")
            or phases_dict.get("2")
            or payload.get("phase_s")
            or payload.get("phase_2")
            or payload.get("fase_s")
            or (payload.get("s") if isinstance(payload.get("s"), dict) else None)
            or payload
        )
        data_t = (
            phases_dict.get("T")
            or phases_dict.get("3")
            or payload.get("phase_t")
            or payload.get("phase_3")
            or payload.get("fase_t")
            or (payload.get("t") if isinstance(payload.get("t"), dict) else None)
            or payload
        )
        return data_r, data_s, data_t, bool(phases_dict)

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @classmethod
    def parsear_instantanea(
        cls,
        payload: dict[str, Any],
        dispositivo: Dispositivo,
        recorded_at: datetime,
    ) -> LecturaInstantanea:
        tipo_instalacion = getattr(dispositivo, "tipo_instalacion", "CONSUMO")
        fases_con_ti_raw = getattr(dispositivo, "fases_con_ti", "R,S,T")
        es_monofasico = AnalizadorCalidadEnergiaService.es_instalacion_monofasica(tipo_instalacion, fases_con_ti_raw)
        fases_con_ti_set = AnalizadorCalidadEnergiaService.fases_con_ti_como_lista(fases_con_ti_raw)

        data_r, data_s, data_t, has_phases = cls._extraer_dict_fases(payload)

        fase_r = parse_fase(data_r, suffix="_r")
        fase_s = parse_fase(data_s, suffix="_s")
        fase_t = parse_fase(data_t, suffix="_t")

        # Preferencia nueva: si el dispositivo declara `orden_fases` o `invertido`,
        # aplicar la configuración consolidada que reordena/rota/invierte según esos campos.
        orden = getattr(dispositivo, "orden_fases", None)
        invertido_flag = getattr(dispositivo, "invertido", False)
        if orden is not None or invertido_flag:
            fase_r, fase_s, fase_t = aplicar_configuracion_ti(
                fase_r, fase_s, fase_t, invertido=invertido_flag, orden_fases=orden
            )
        else:
            fase_r, fase_s, fase_t = _aplicar_fases_invertidas(fase_r, fase_s, fase_t, dispositivo)
            fase_r, fase_s, fase_t = _aplicar_rotacion_angulos(fase_r, fase_s, fase_t, dispositivo)

        if "R" not in fases_con_ti_set:
            fase_r = AnalizadorCalidadEnergiaService.sanear_fase_sin_ti(fase_r)
        if "S" not in fases_con_ti_set:
            fase_s = AnalizadorCalidadEnergiaService.sanear_fase_sin_ti(fase_s)
        if "T" not in fases_con_ti_set:
            fase_t = AnalizadorCalidadEnergiaService.sanear_fase_sin_ti(fase_t)

        total = payload.get("total") or payload.get("tot")
        total_data = total if isinstance(total, dict) else payload

        p_tot, q_tot, s_tot, fp_tot = _calcular_totales_potencia(total_data, fase_r, fase_s, fase_t, has_phases)
        desbalance_v, voltage_linea_V, i_neutro, v_neutro = _calcular_derivadas_red(
            fase_r, fase_s, fase_t, es_monofasico
        )
        thd_v_prom, thd_i_tot = _calcular_totales_thd(total_data, payload, fase_r, fase_s, fase_t)

        lectura = LecturaInstantanea(
            id=None,
            dispositivo_id=dispositivo.id,
            registrado_en=recorded_at,
            fase_r=fase_r,
            fase_s=fase_s,
            fase_t=fase_t,
            potencia_activa_total=PotenciaActiva(vatios=p_tot) if p_tot is not None else None,
            potencia_reactiva_total=PotenciaReactiva(var=q_tot) if q_tot is not None else None,
            potencia_aparente_total=PotenciaAparente(va=s_tot) if s_tot is not None else None,
            factor_potencia_total=FactorPotencia(valor=fp_tot) if fp_tot is not None else None,
            desbalance_tension_porcentaje=desbalance_v,
            corriente_neutro_estimada=i_neutro,
            voltage_linea_V=voltage_linea_V,
            tension_neutro_estimada=v_neutro,
            thd_v_promedio_porcentaje=thd_v_prom,
            thd_i_total_porcentaje=thd_i_tot,
        )
        diag_inst = EvaluadorDiagnosticoInstalacionService.evaluar_diagnostico(
            lectura=lectura,
            fases_con_ti=fases_con_ti_set,
            dispositivo_id=dispositivo.id,
        )
        return replace(lectura, diagnostico_instalacion=diag_inst)

    @staticmethod
    def parsear_acumulado(
        payload: dict[str, Any], dispositivo_id: str, recorded_at: datetime, **kwargs: Any
    ) -> AcumuladoEnergia:
        # Si se pasó `orden_fases` (array o string) y/o `invertido`, convertirlo a
        # la forma entendida por EnergiaPayloadParser: `correccion_angular` (dict)
        orden = kwargs.pop("orden_fases", None)
        invertido = kwargs.pop("invertido", False)
        if orden:
            # normalizar orden
            if isinstance(orden, str):
                orden_norm = [s.strip().upper() for s in orden.split(",") if s.strip()]
            else:
                orden_norm = [str(s).strip().upper() for s in orden if str(s).strip()]
            etiquetas = ["R", "S", "T"]
            angulos_map: dict[str, float] = {}
            for i, etiqueta in enumerate(etiquetas):
                if etiqueta in orden_norm:
                    pos = orden_norm.index(etiqueta)
                    shift = pos - i
                    if shift != 0:
                        angulos_map[etiqueta] = float(-120.0 * shift)
            if angulos_map:
                kwargs["correccion_angular"] = angulos_map
        if invertido:
            kwargs["invertido"] = True

        return EnergiaPayloadParser.parsear_acumulado(payload, dispositivo_id, recorded_at, **kwargs)

    @staticmethod
    def parsear_log_estado(
        payload: dict[str, Any],
        dispositivo_id: str,
        recorded_at: datetime,
    ) -> LogEstadoDispositivo:
        wifi_raw = payload.get("wifi_sta")
        wifi_info: dict[str, Any] = wifi_raw if isinstance(wifi_raw, dict) else {}
        device_raw = payload.get("device_info")
        device_info: dict[str, Any] = device_raw if isinstance(device_raw, dict) else {}
        return LogEstadoDispositivo(
            id=None,
            dispositivo_id=dispositivo_id,
            registrado_en=recorded_at,
            wifi_rssi_dbm=sanear_entero(wifi_info.get("dbm")),
            wifi_calidad=sanear_entero(wifi_info.get("quality")),
            direccion_ip=sanear_ip(wifi_info.get("ip")),
            tiempo_activo_segundos=sanear_entero(payload.get("uptime") or device_info.get("uptime")),
            payload_bruto=acotar_payload_bruto(payload),
        )

    @staticmethod
    def parsear_alerta_evento(payload: dict[str, Any], dispositivo_id: str) -> AlertaDispositivo:
        return AlertaDispositivo(
            id=None,
            dispositivo_id=dispositivo_id,
            tipo_alerta="EVENTO_DISPOSITIVO",
            severidad=SeveridadAlerta.INFO,
            mensaje=str(payload.get("event") or payload),
        )


__all__ = [
    "TelemetriaPayloadParser",
    "acotar_payload_bruto",
    "parse_fase",
    "parse_timestamp",
    "sanear_entero",
    "sanear_ip",
]

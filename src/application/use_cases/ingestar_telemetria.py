import uuid
from datetime import datetime, timezone
from typing import Any

from src.domain.telemetria.entities import (
    AcumuladoEnergia,
    AlertaDispositivo,
    Dispositivo,
    LecturaInstantanea,
    LogEstadoDispositivo,
    MedicionFase,
)
from src.domain.telemetria.ports import (
    LoggerPort,
    PublicadorEventosPort,
    RepositorioDispositivosPort,
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.services import AnalizadorCalidadEnergiaService
from src.domain.telemetria.value_objects import (
    Corriente,
    EnergiaActiva,
    EnergiaReactiva,
    EstadoDispositivo,
    FactorPotencia,
    MacAddress,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    SeveridadAlerta,
    Tension,
)


class IngestarTelemetriaUseCase:
    def __init__(
        self,
        repo_dispositivos: RepositorioDispositivosPort,
        repo_telemetria: RepositorioTelemetriaPort,
        publicador: PublicadorEventosPort | None = None,
        logger: LoggerPort | None = None,
    ):
        self.repo_dispositivos = repo_dispositivos
        self.repo_telemetria = repo_telemetria
        self.publicador = publicador
        self.logger = logger

    def _parse_timestamp(self, ts_val: Any) -> datetime:
        if ts_val:
            try:
                if isinstance(ts_val, (int, float)) and ts_val > 1000000000:
                    return datetime.fromtimestamp(ts_val, tz=timezone.utc)
                elif isinstance(ts_val, str):
                    return datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
            except Exception:
                pass
        return datetime.now(timezone.utc)

    def _obtener_o_crear_dispositivo(self, mac_raw: str, dev_info: dict[str, Any] | None = None) -> Dispositivo:
        mac_vo = MacAddress(mac_raw)
        dispositivo = self.repo_dispositivos.obtener_por_uid(mac_vo)
        if not dispositivo:
            nuevo = Dispositivo(
                id=str(uuid.uuid4()),
                device_uid=mac_vo,
                nombre=f"Powermeter-{mac_vo.valor[-4:]}",
                modelo=dev_info.get("device_model", "SmartPlus") if dev_info else "SmartPlus",
                numero_serie=dev_info.get("serial_number") if dev_info else None,
                version_hw=dev_info.get("hw_model") if dev_info else None,
                version_fw=dev_info.get("device_fw") if dev_info else None,
                estado=EstadoDispositivo.ONLINE,
                visto_por_ultima_vez=datetime.now(timezone.utc),
            )
            saved = self.repo_dispositivos.guardar(nuevo)
            if self.logger:
                self.logger.info("nuevo_dispositivo_registrado", device_uid=mac_vo.valor, modelo=nuevo.modelo)
            return saved
        else:
            dispositivo.marcar_online(datetime.now(timezone.utc))
            if dev_info:
                if dev_info.get("serial_number"):
                    dispositivo.numero_serie = dev_info.get("serial_number")
                if dev_info.get("device_fw"):
                    dispositivo.version_fw = dev_info.get("device_fw")
                if dev_info.get("hw_model"):
                    dispositivo.version_hw = dev_info.get("hw_model")
            return self.repo_dispositivos.guardar(dispositivo)

    def _parse_fase(self, data: Any, suffix: str = "") -> MedicionFase:
        if not isinstance(data, dict):
            return MedicionFase()

        sfx_lower = suffix.lower()
        sfx_upper = suffix.upper()
        sfx_no_underscore = suffix.replace("_", "")

        def _get(*keys: str) -> Any:
            for k in keys:
                val = data.get(k)
                if val is not None:
                    return val
            return None

        v = _get(
            f"voltage_V{suffix}",
            f"m_v{suffix}",
            f"voltage{suffix}",
            f"v{sfx_lower}",
            f"V{sfx_upper}",
            f"v{sfx_no_underscore}",
            f"V{sfx_no_underscore}",
            "voltage_V",
            "voltage",
            "v",
            "V",
        )
        i = _get(
            f"current_A{suffix}",
            f"m_i{suffix}",
            f"current{suffix}",
            f"i{sfx_lower}",
            f"I{sfx_upper}",
            f"i{sfx_no_underscore}",
            f"I{sfx_no_underscore}",
            "current_A",
            "current",
            "i",
            "I",
        )
        p = _get(
            f"net_active_power_W{suffix}",
            f"m_p{suffix}",
            f"active_power{suffix}",
            f"p{sfx_lower}",
            f"P{sfx_upper}",
            f"p{sfx_no_underscore}",
            f"P{sfx_no_underscore}",
            "net_active_power_W",
            "active_power",
            "p",
            "P",
        )
        q = _get(
            f"net_reactive_power_VAR{suffix}",
            f"m_q{suffix}",
            f"reactive_power{suffix}",
            f"q{sfx_lower}",
            f"Q{sfx_upper}",
            f"q{sfx_no_underscore}",
            f"Q{sfx_no_underscore}",
            "net_reactive_power_VAR",
            "reactive_power",
            "q",
            "Q",
        )
        s = _get(
            f"net_apparent_power_VA{suffix}",
            f"m_s{suffix}",
            f"apparent_power{suffix}",
            f"s{sfx_lower}",
            f"S{sfx_upper}",
            f"s{sfx_no_underscore}",
            f"S{sfx_no_underscore}",
            "net_apparent_power_VA",
            "apparent_power",
            "s",
            "S",
        )
        fp = _get(
            f"power_factor{suffix}",
            f"m_pf{suffix}",
            f"pf{suffix}",
            f"fp{suffix}",
            f"pf{sfx_lower}",
            f"PF{sfx_upper}",
            f"fp{sfx_lower}",
            f"FP{sfx_upper}",
            "power_factor",
            "pf",
            "fp",
        )

        return MedicionFase(
            tension=Tension(voltios=float(v)) if v is not None else None,
            corriente=Corriente(amperios=float(i)) if i is not None else None,
            potencia_activa=PotenciaActiva(vatios=float(p)) if p is not None else None,
            potencia_reactiva=PotenciaReactiva(var=float(q)) if q is not None else None,
            potencia_aparente=PotenciaAparente(va=float(s)) if s is not None else None,
            factor_potencia=FactorPotencia(valor=float(fp)) if fp is not None else None,
        )

    def ejecutar(self, topico: str, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return

        if self.publicador:
            self.publicador.publicar_telemetria_en_vivo(topico, payload)

        partes = topico.split("/")
        if len(partes) < 4:
            return

        mac_raw = partes[2]
        subtopico = partes[3]

        dev_info = payload.get("device_info") if isinstance(payload.get("device_info"), dict) else None
        dispositivo = self._obtener_o_crear_dispositivo(mac_raw, dev_info)
        recorded_at = self._parse_timestamp(payload.get("timestamp") or payload.get("t") or payload.get("time"))

        if subtopico == "inst":
            # Extraer fases de estructura de arreglo 'f': [{"n":"R","v":223.4,...}, ...]
            phases_dict: dict[str, dict[str, Any]] = {}
            if isinstance(payload.get("f"), list):
                for item in payload["f"]:
                    if isinstance(item, dict) and "n" in item:
                        phases_dict[str(item["n"]).strip().upper()] = item

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

            fase_r = self._parse_fase(data_r, suffix="_r")
            fase_s = self._parse_fase(data_s, suffix="_s")
            fase_t = self._parse_fase(data_t, suffix="_t")

            total = payload.get("total") or payload.get("tot")
            total_data = total if isinstance(total, dict) else payload

            p_tot = (
                total_data.get("net_active_power_W")
                or total_data.get("m_p_tot")
                or total_data.get("total_active_power")
                or total_data.get("p_tot")
                or total_data.get("P_tot")
            )
            if p_tot is None and not phases_dict:
                p_tot = total_data.get("p")
            if p_tot is None:
                p_vals = [f.potencia_activa.vatios for f in (fase_r, fase_s, fase_t) if f.potencia_activa is not None]
                if p_vals:
                    p_tot = sum(p_vals)

            q_tot = (
                total_data.get("net_reactive_power_VAR")
                or total_data.get("m_q_tot")
                or total_data.get("total_reactive_power")
                or total_data.get("q_tot")
                or total_data.get("Q_tot")
            )
            if q_tot is None and not phases_dict:
                q_tot = total_data.get("q")
            if q_tot is None:
                q_vals = [f.potencia_reactiva.var for f in (fase_r, fase_s, fase_t) if f.potencia_reactiva is not None]
                if q_vals:
                    q_tot = sum(q_vals)

            s_tot = (
                total_data.get("net_apparent_power_VA")
                or total_data.get("m_s_tot")
                or total_data.get("total_apparent_power")
                or total_data.get("s_tot")
                or total_data.get("S_tot")
            )
            if s_tot is None and not phases_dict:
                s_tot = total_data.get("s")
            if s_tot is None:
                s_vals = [f.potencia_aparente.va for f in (fase_r, fase_s, fase_t) if f.potencia_aparente is not None]
                if s_vals:
                    s_tot = sum(s_vals)

            fp_tot = (
                total_data.get("power_factor")
                or total_data.get("m_pf_tot")
                or total_data.get("total_power_factor")
                or total_data.get("fp_tot")
                or total_data.get("pf_tot")
            )
            if fp_tot is None and not phases_dict:
                fp_tot = total_data.get("fp") or total_data.get("pf")
            if fp_tot is None and p_tot is not None and s_tot is not None and float(s_tot) > 0:
                fp_tot = round(float(p_tot) / float(s_tot), 2)

            lectura = LecturaInstantanea(
                id=None,
                dispositivo_id=dispositivo.id,
                registrado_en=recorded_at,
                fase_r=fase_r,
                fase_s=fase_s,
                fase_t=fase_t,
                potencia_activa_total=PotenciaActiva(vatios=float(p_tot)) if p_tot is not None else None,
                potencia_reactiva_total=PotenciaReactiva(var=float(q_tot)) if q_tot is not None else None,
                potencia_aparente_total=PotenciaAparente(va=float(s_tot)) if s_tot is not None else None,
                factor_potencia_total=FactorPotencia(valor=float(fp_tot)) if fp_tot is not None else None,
            )
            self.repo_telemetria.guardar_instantanea(lectura)
            if self.logger:
                self.logger.debug(
                    "telemetria_instantanea_guardada",
                    device_uid=dispositivo.device_uid.valor,
                    p_activa_W=float(p_tot) if p_tot is not None else None,
                    fp=float(fp_tot) if fp_tot is not None else None,
                )

            # Evaluación de alertas de dominio
            alerta = AnalizadorCalidadEnergiaService.evaluar_alerta_tension(dispositivo.id, lectura)
            if alerta:
                self.repo_telemetria.guardar_alerta(alerta)
                if self.logger:
                    self.logger.warning(
                        "alerta_calidad_energia_detectada",
                        dispositivo_id=dispositivo.id,
                        tipo=alerta.tipo_alerta,
                        severidad=alerta.severidad.value,
                        mensaje=alerta.mensaje,
                    )

        elif subtopico in ("acc", "energyio"):
            total = payload.get("total") if isinstance(payload.get("total"), dict) else payload
            if not isinstance(total, dict):
                total = {}

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

            # Soporte para formato compacto de Powermeter con arreglo 'f': [{"n":"R","a":0.03,"r":0.01}, ...]
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

            acumulado = AcumuladoEnergia(
                id=None,
                dispositivo_id=dispositivo.id,
                registrado_en=recorded_at,
                energia_activa_neta=EnergiaActiva(kwh=float(e_act)) if e_act is not None else None,
                energia_reactiva_neta=EnergiaReactiva(kvarh=float(e_react)) if e_react is not None else None,
                energia_activa_importada=EnergiaActiva(kwh=float(e_act_imp)) if e_act_imp is not None else None,
                energia_activa_exportada=EnergiaActiva(kwh=float(e_act_exp)) if e_act_exp is not None else None,
                energia_reactiva_importada=EnergiaReactiva(kvarh=float(e_react_imp))
                if e_react_imp is not None
                else None,
                energia_reactiva_exportada=EnergiaReactiva(kvarh=float(e_react_exp))
                if e_react_exp is not None
                else None,
            )
            self.repo_telemetria.guardar_energia(acumulado)
            if self.logger:
                self.logger.debug(
                    "telemetria_energia_guardada",
                    device_uid=dispositivo.device_uid.valor,
                    kwh=float(e_act) if e_act is not None else None,
                )

        elif subtopico == "status":
            wifi_raw = payload.get("wifi_sta")
            wifi_info: dict[str, Any] = wifi_raw if isinstance(wifi_raw, dict) else {}
            device_raw = payload.get("device_info")
            device_info: dict[str, Any] = device_raw if isinstance(device_raw, dict) else {}
            log = LogEstadoDispositivo(
                id=None,
                dispositivo_id=dispositivo.id,
                registrado_en=recorded_at,
                wifi_rssi_dbm=wifi_info.get("dbm"),
                wifi_calidad=wifi_info.get("quality"),
                direccion_ip=wifi_info.get("ip"),
                tiempo_activo_segundos=payload.get("uptime") or device_info.get("uptime"),
                payload_bruto=payload,
            )
            self.repo_telemetria.guardar_log_estado(log)

        elif subtopico == "event":
            alerta = AlertaDispositivo(
                id=None,
                dispositivo_id=dispositivo.id,
                tipo_alerta="EVENTO_DISPOSITIVO",
                severidad=SeveridadAlerta.INFO,
                mensaje=str(payload.get("event") or payload),
            )
            self.repo_telemetria.guardar_alerta(alerta)

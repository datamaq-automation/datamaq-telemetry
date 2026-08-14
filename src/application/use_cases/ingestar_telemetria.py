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

    def _parse_fase(self, data: dict[str, Any], suffix: str = "") -> MedicionFase:
        v = (
            data.get(f"voltage_V{suffix}")
            or data.get(f"m_v{suffix}")
            or data.get(f"voltage{suffix}")
            or data.get("voltage_V")
            or data.get("voltage")
        )
        i = (
            data.get(f"current_A{suffix}")
            or data.get(f"m_i{suffix}")
            or data.get(f"current{suffix}")
            or data.get("current_A")
            or data.get("current")
        )
        p = (
            data.get(f"net_active_power_W{suffix}")
            or data.get(f"m_p{suffix}")
            or data.get(f"active_power{suffix}")
            or data.get("net_active_power_W")
            or data.get("active_power")
        )
        q = (
            data.get(f"net_reactive_power_VAR{suffix}")
            or data.get(f"m_q{suffix}")
            or data.get(f"reactive_power{suffix}")
            or data.get("net_reactive_power_VAR")
            or data.get("reactive_power")
        )
        s = (
            data.get(f"net_apparent_power_VA{suffix}")
            or data.get(f"m_s{suffix}")
            or data.get(f"apparent_power{suffix}")
            or data.get("net_apparent_power_VA")
            or data.get("apparent_power")
        )
        fp = (
            data.get(f"power_factor{suffix}")
            or data.get(f"m_pf{suffix}")
            or data.get(f"pf{suffix}")
            or data.get("power_factor")
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
        if self.publicador:
            self.publicador.publicar_telemetria_en_vivo(topico, payload)

        partes = topico.split("/")
        if len(partes) < 4:
            return

        mac_raw = partes[2]
        subtopico = partes[3]

        dev_info = payload.get("device_info") if isinstance(payload, dict) else None
        dispositivo = self._obtener_o_crear_dispositivo(mac_raw, dev_info)
        recorded_at = self._parse_timestamp(payload.get("timestamp"))

        if subtopico == "inst":
            fase_r = self._parse_fase(payload.get("phase_r", payload), suffix="_r")
            fase_s = self._parse_fase(payload.get("phase_s", payload), suffix="_s")
            fase_t = self._parse_fase(payload.get("phase_t", payload), suffix="_t")
            total = payload.get("total", payload)

            p_tot = total.get("net_active_power_W") or total.get("m_p_tot") or total.get("total_active_power")
            q_tot = total.get("net_reactive_power_VAR") or total.get("m_q_tot") or total.get("total_reactive_power")
            s_tot = total.get("net_apparent_power_VA") or total.get("m_s_tot") or total.get("total_apparent_power")
            fp_tot = total.get("power_factor") or total.get("m_pf_tot") or total.get("total_power_factor")

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
            total = payload.get("total", payload)
            e_act = total.get("net_active_energy_KWH")
            e_react = total.get("net_reactive_energy_KVARH")
            e_act_imp = total.get("imported_active_energy_KWH")
            e_act_exp = total.get("exported_active_energy_KWH")
            e_react_imp = total.get("imported_reactive_energy_KVARH")
            e_react_exp = total.get("exported_reactive_energy_KVARH")

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

        elif subtopico == "status":
            wifi_info = payload.get("wifi_sta", {})
            log = LogEstadoDispositivo(
                id=None,
                dispositivo_id=dispositivo.id,
                registrado_en=recorded_at,
                wifi_rssi_dbm=wifi_info.get("dbm"),
                wifi_calidad=wifi_info.get("quality"),
                direccion_ip=wifi_info.get("ip"),
                tiempo_activo_segundos=payload.get("uptime") or payload.get("device_info", {}).get("uptime"),
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

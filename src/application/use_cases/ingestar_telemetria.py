import ipaddress
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar

from src.application.mappers.alerta_mapper import AlertaMapper
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
from src.domain.telemetria.services import (
    AnalizadorCalidadEnergiaService,
    FiltroPersistenciaTemporalService,
)
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
    # Memoria estática de últimas persistencias por dispositivo para compartir entre invocaciones
    _ultimas_persistencias: ClassVar[dict[str, datetime]] = {}
    _device_cache: ClassVar[dict[str, Dispositivo]] = {}
    _ultimos_heartbeats: ClassVar[dict[str, datetime]] = {}
    _filtro_persistencia: ClassVar[FiltroPersistenciaTemporalService] = FiltroPersistenciaTemporalService()
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(
        self,
        repo_dispositivos: RepositorioDispositivosPort,
        repo_telemetria: RepositorioTelemetriaPort,
        publicador: PublicadorEventosPort | None = None,
        logger: LoggerPort | None = None,
        granularidad_segundos: int = 300,
        permitir_auto_registro: bool = True,
    ):
        self.repo_dispositivos = repo_dispositivos
        self.repo_telemetria = repo_telemetria
        self.publicador = publicador
        self.logger = logger
        self.granularidad_segundos = granularidad_segundos
        self.permitir_auto_registro = permitir_auto_registro

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

    def _obtener_o_crear_dispositivo(
        self, mac_raw: str, dev_info: dict[str, Any] | None = None, ahora: datetime | None = None
    ) -> Dispositivo | None:
        mac_vo = MacAddress(mac_raw)
        if ahora is None:
            ahora = datetime.now(timezone.utc)

        with self._lock:
            # 1. Búsqueda en caché en memoria
            if mac_vo.valor in self._device_cache:
                dispositivo = self._device_cache[mac_vo.valor]
                ultimo_hb = self._ultimos_heartbeats.get(dispositivo.id)

                # Si venció la ventana de amortiguación (60s), persistir estado en DB
                if ultimo_hb is None or (ahora - ultimo_hb).total_seconds() >= 60:
                    dispositivo.marcar_online(ahora)
                    if dev_info:
                        if dev_info.get("serial_number"):
                            dispositivo.numero_serie = dev_info.get("serial_number")
                        if dev_info.get("device_fw"):
                            dispositivo.version_fw = dev_info.get("device_fw")
                        if dev_info.get("hw_model"):
                            dispositivo.version_hw = dev_info.get("hw_model")
                    dispositivo = self.repo_dispositivos.guardar(dispositivo)
                    self._device_cache[mac_vo.valor] = dispositivo
                    self._ultimos_heartbeats[dispositivo.id] = ahora

                return dispositivo

            # 2. Si no está en caché, consultar repositorio
            dispositivo = self.repo_dispositivos.obtener_por_uid(mac_vo)
            if not dispositivo:
                if not self.permitir_auto_registro:
                    if self.logger:
                        self.logger.info("dispositivo_no_registrado_descartado", device_uid=mac_vo.valor)
                    return None
                nuevo = Dispositivo(
                    id=str(uuid.uuid4()),
                    device_uid=mac_vo,
                    nombre=f"Powermeter-{mac_vo.valor[-4:]}",
                    modelo=dev_info.get("device_model", "SmartPlus") if dev_info else "SmartPlus",
                    numero_serie=dev_info.get("serial_number") if dev_info else None,
                    version_hw=dev_info.get("hw_model") if dev_info else None,
                    version_fw=dev_info.get("device_fw") if dev_info else None,
                    estado=EstadoDispositivo.ONLINE,
                    visto_por_ultima_vez=ahora,
                )
                saved = self.repo_dispositivos.guardar(nuevo)
                self._device_cache[mac_vo.valor] = saved
                self._ultimos_heartbeats[saved.id] = ahora
                if self.logger:
                    self.logger.info("nuevo_dispositivo_registrado", device_uid=mac_vo.valor, modelo=nuevo.modelo)
                return saved
            else:
                dispositivo.marcar_online(ahora)
                if dev_info:
                    if dev_info.get("serial_number"):
                        dispositivo.numero_serie = dev_info.get("serial_number")
                    if dev_info.get("device_fw"):
                        dispositivo.version_fw = dev_info.get("device_fw")
                    if dev_info.get("hw_model"):
                        dispositivo.version_hw = dev_info.get("hw_model")
                saved = self.repo_dispositivos.guardar(dispositivo)
                self._device_cache[mac_vo.valor] = saved
                self._ultimos_heartbeats[saved.id] = ahora
                return saved

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
        thd_v = _get(
            f"thd_v_pct{suffix}",
            f"thd_v{suffix}",
            f"thd_v_porcentaje{suffix}",
            f"thdv{suffix}",
            f"tv{suffix}",
            "thd_v_pct",
            "thd_v",
            "thdv",
            "tv",
        )
        thd_i = _get(
            f"thd_i_pct{suffix}",
            f"thd_i{suffix}",
            f"thd_i_porcentaje{suffix}",
            f"thdi{suffix}",
            f"ti{suffix}",
            "thd_i_pct",
            "thd_i",
            "thdi",
            "ti",
        )

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
        recorded_at = self._parse_timestamp(payload.get("timestamp") or payload.get("t") or payload.get("time"))
        dispositivo = self._obtener_o_crear_dispositivo(mac_raw, dev_info, ahora=recorded_at)

        if dispositivo is None:
            return

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

            vr = fase_r.tension.voltios if fase_r.tension else None
            vs = fase_s.tension.voltios if fase_s.tension else None
            vt = fase_t.tension.voltios if fase_t.tension else None
            desbalance_v = AnalizadorCalidadEnergiaService.calcular_desbalance_tension(vr, vs, vt)

            # Calcular tensión línea-línea (L-L) asumiendo sistema balanceado
            # V_LL = sqrt(3) * V_FN (promedio de las tres fases)
            tensiones_fase = [v for v in (vr, vs, vt) if v is not None]
            voltage_linea_V = None
            if tensiones_fase:
                promedio_fase = sum(tensiones_fase) / len(tensiones_fase)
                voltage_linea_V = round(promedio_fase * 1.7320508075688772, 2)  # sqrt(3)

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
                desbalance_tension_porcentaje=desbalance_v,
                corriente_neutro_estimada=i_neutro,
                voltage_linea_V=voltage_linea_V,
                tension_neutro_estimada=v_neutro,
                thd_v_promedio_porcentaje=round(float(thd_v_prom), 2) if thd_v_prom is not None else None,
                thd_i_total_porcentaje=round(float(thd_i_tot), 2) if thd_i_tot is not None else None,
            )
            # Evaluación de alertas de dominio (se evalúa siempre para cada paquete recibido)
            # 1. Tensión y falta de fase con filtro de persistencia temporal (anti-falsos positivos)
            alerta_tension_raw = AnalizadorCalidadEnergiaService.evaluar_alerta_tension(dispositivo.id, lectura)
            alerta_tension = self._filtro_persistencia.procesar_alerta(
                dispositivo.id, alerta_tension_raw, categoria="TENSION", ahora=recorded_at
            )
            if alerta_tension:
                self.repo_telemetria.guardar_alerta(alerta_tension)
                if self.publicador:
                    self.publicador.publicar_telemetria_en_vivo(
                        f"m/wifi/{mac_raw}/alertas",
                        AlertaMapper.to_dto(alerta_tension).model_dump(mode="json"),
                    )
                if self.logger:
                    self.logger.warning(
                        "alerta_calidad_energia_detectada",
                        dispositivo_id=dispositivo.id,
                        tipo=alerta_tension.tipo_alerta,
                        severidad=alerta_tension.severidad.value,
                        mensaje=alerta_tension.mensaje,
                    )

            # 2. Desbalance trifásico (VUR)
            alerta_desbalance_raw = AnalizadorCalidadEnergiaService.evaluar_alerta_desbalance(dispositivo.id, lectura)
            alerta_desbalance = self._filtro_persistencia.procesar_alerta(
                dispositivo.id, alerta_desbalance_raw, categoria="DESBALANCE_TENSION", ahora=recorded_at
            )
            if alerta_desbalance:
                self.repo_telemetria.guardar_alerta(alerta_desbalance)
                if self.publicador:
                    self.publicador.publicar_telemetria_en_vivo(
                        f"m/wifi/{mac_raw}/alertas",
                        AlertaMapper.to_dto(alerta_desbalance).model_dump(mode="json"),
                    )
                if self.logger:
                    self.logger.warning(
                        "alerta_calidad_energia_detectada",
                        dispositivo_id=dispositivo.id,
                        tipo=alerta_desbalance.tipo_alerta,
                        severidad=alerta_desbalance.severidad.value,
                        mensaje=alerta_desbalance.mensaje,
                    )

            # 3. Detección de Polaridad de Transformador de Corriente (TI Invertido)
            fases_ti_list = [f.strip().upper() for f in getattr(dispositivo, "fases_con_ti", "R,S,T").split(",")]
            alertas_ti_raw = AnalizadorCalidadEnergiaService.evaluar_alerta_ti_invertido(
                dispositivo_id=dispositivo.id,
                lectura=lectura,
                tipo_instalacion=getattr(dispositivo, "tipo_instalacion", "CONSUMO"),
                fases_con_ti=fases_ti_list,
            )
            for a_ti in alertas_ti_raw:
                a_ti_filtrada = self._filtro_persistencia.procesar_alerta(
                    dispositivo.id, a_ti, categoria=f"TI_INVERTIDO_{a_ti.mensaje[:50]}", ahora=recorded_at
                )
                if a_ti_filtrada:
                    self.repo_telemetria.guardar_alerta(a_ti_filtrada)
                    if self.publicador:
                        self.publicador.publicar_telemetria_en_vivo(
                            f"m/wifi/{mac_raw}/alertas",
                            AlertaMapper.to_dto(a_ti_filtrada).model_dump(mode="json"),
                        )
                    if self.logger:
                        self.logger.warning(
                            "alerta_calidad_energia_detectada",
                            dispositivo_id=dispositivo.id,
                            tipo=a_ti_filtrada.tipo_alerta,
                            severidad=a_ti_filtrada.severidad.value,
                            mensaje=a_ti_filtrada.mensaje,
                        )

            # 4. Factor de potencia bajo (penalización tarifaria ENRE)
            alerta_fp_raw = AnalizadorCalidadEnergiaService.evaluar_alerta_factor_potencia(dispositivo.id, lectura)
            alerta_fp = self._filtro_persistencia.procesar_alerta(
                dispositivo.id, alerta_fp_raw, categoria="FACTOR_POTENCIA", ahora=recorded_at
            )
            if alerta_fp:
                self.repo_telemetria.guardar_alerta(alerta_fp)
                if self.publicador:
                    self.publicador.publicar_telemetria_en_vivo(
                        f"m/wifi/{mac_raw}/alertas",
                        AlertaMapper.to_dto(alerta_fp).model_dump(mode="json"),
                    )
                if self.logger:
                    self.logger.warning(
                        "alerta_calidad_energia_detectada",
                        dispositivo_id=dispositivo.id,
                        tipo=alerta_fp.tipo_alerta,
                        severidad=alerta_fp.severidad.value,
                        mensaje=alerta_fp.mensaje,
                    )

            # 5. Distorsión Armónica Total (THD) y Riesgo de Resonancia
            alertas_thd_raw = AnalizadorCalidadEnergiaService.evaluar_alertas_distorsion_armonica(
                dispositivo.id, lectura
            )
            for a_thd in alertas_thd_raw:
                a_thd_filtrada = self._filtro_persistencia.procesar_alerta(
                    dispositivo.id,
                    a_thd,
                    categoria=f"DISTORSION_ARMONICA_{a_thd.tipo_alerta}_{a_thd.fase or 'ALL'}",
                    ahora=recorded_at,
                )
                if a_thd_filtrada:
                    self.repo_telemetria.guardar_alerta(a_thd_filtrada)
                    if self.publicador:
                        self.publicador.publicar_telemetria_en_vivo(
                            f"m/wifi/{mac_raw}/alertas",
                            AlertaMapper.to_dto(a_thd_filtrada).model_dump(mode="json"),
                        )
                    if self.logger:
                        self.logger.warning(
                            "alerta_calidad_energia_detectada",
                            dispositivo_id=dispositivo.id,
                            tipo=a_thd_filtrada.tipo_alerta,
                            severidad=a_thd_filtrada.severidad.value,
                            mensaje=a_thd_filtrada.mensaje,
                        )

            # Auto-despeje de perturbaciones normalizadas con difusión en vivo
            if alerta_tension_raw is None:
                self._auto_resolver_alertas_si_corresponde(
                    dispositivo.id, mac_raw, ["BAJA_TENSION", "SOBRETENSION", "FALTA_FASE"], recorded_at
                )
            if alerta_desbalance_raw is None:
                self._auto_resolver_alertas_si_corresponde(dispositivo.id, mac_raw, ["DESBALANCE_TENSION"], recorded_at)
            if not alertas_ti_raw:
                self._auto_resolver_alertas_si_corresponde(dispositivo.id, mac_raw, ["TI_INVERTIDO"], recorded_at)
            if alerta_fp_raw is None:
                self._auto_resolver_alertas_si_corresponde(
                    dispositivo.id, mac_raw, ["BAJO_FACTOR_POTENCIA"], recorded_at
                )
            if not alertas_thd_raw:
                self._auto_resolver_alertas_si_corresponde(
                    dispositivo.id,
                    mac_raw,
                    [
                        "ALTO_THD_TENSION_WARNING",
                        "ALTO_THD_TENSION_CRITICAL",
                        "ALTO_THD_CORRIENTE",
                        "RIESGO_RESONANCIA_CAPACITORES",
                    ],
                    recorded_at,
                )

            # Persistencia con downsampling según granularidad configurada
            debe_persistir = True
            if self.granularidad_segundos > 0:
                with self._lock:
                    ultima = self._ultimas_persistencias.get(dispositivo.id)
                    if ultima is not None and (recorded_at - ultima).total_seconds() < self.granularidad_segundos:
                        debe_persistir = False

            if debe_persistir:
                self.repo_telemetria.guardar_instantanea(lectura)
                with self._lock:
                    self._ultimas_persistencias[dispositivo.id] = recorded_at
                if self.logger:
                    self.logger.debug(
                        "telemetria_instantanea_guardada",
                        device_uid=dispositivo.device_uid.valor,
                        p_activa_W=float(p_tot) if p_tot is not None else None,
                        fp=float(fp_tot) if fp_tot is not None else None,
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
                wifi_rssi_dbm=sanear_entero(wifi_info.get("dbm")),
                wifi_calidad=sanear_entero(wifi_info.get("quality")),
                direccion_ip=sanear_ip(wifi_info.get("ip")),
                tiempo_activo_segundos=sanear_entero(payload.get("uptime") or device_info.get("uptime")),
                payload_bruto=acotar_payload_bruto(payload),
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

    def _auto_resolver_alertas_si_corresponde(
        self,
        dispositivo_id: str,
        mac_raw: str,
        tipos_alerta: list[str],
        recorded_at: datetime,
    ) -> None:
        """Despeja automáticamente alertas abiertas de los tipos indicados al normalizarse la variable."""
        alertas_abiertas = self.repo_telemetria.listar_alertas(
            dispositivo_id=dispositivo_id,
            solo_abiertas=True,
        )
        for a in alertas_abiertas:
            if a.tipo_alerta in tipos_alerta:
                a.marcar_resuelta(
                    recorded_at,
                    observaciones="Despeje automático: la variable normalizó su valor dentro del rango admisible.",
                )
                self.repo_telemetria.guardar_alerta(a)
                if self.publicador:
                    self.publicador.publicar_telemetria_en_vivo(
                        f"m/wifi/{mac_raw}/alertas",
                        AlertaMapper.to_dto(a).model_dump(mode="json"),
                    )
                if self.logger:
                    self.logger.info(
                        "alerta_auto_resuelta_normalizada",
                        dispositivo_id=dispositivo_id,
                        tipo=a.tipo_alerta,
                        duracion_segundos=a.duracion_segundos,
                    )


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

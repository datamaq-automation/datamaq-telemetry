"""src/application/use_cases/ingestar_telemetria.py."""

import math
import threading
from datetime import datetime
from typing import Any, ClassVar

from src.application.mappers.payload_telemetria_parser import (
    TelemetriaPayloadParser,
    acotar_payload_bruto,
    parse_fase,
    parse_timestamp,
    sanear_entero,
    sanear_ip,
)
from src.application.mappers.telemetria_mapper import TelemetriaMapper
from src.application.use_cases.gestionar_disponibilidad import (
    GestionarDisponibilidadUseCase,
)
from src.application.use_cases.ingesta.capturador_campana import (
    CapturadorCampanaIngesta,
)
from src.application.use_cases.ingesta.procesador_alertas_ingesta import (
    ProcesadorAlertasIngesta,
)
from src.application.use_cases.ingesta.resolvedor_dispositivo import (
    ResolvedorDispositivoIngesta,
)
from src.domain.telemetria.entities import Dispositivo, MedicionFase
from src.domain.telemetria.ports import (
    LoggerPort,
    PublicadorEventosPort,
    RepositorioDispositivosPort,
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.services import FiltroPersistenciaTemporalService
from src.domain.telemetria.servicios.analizador_calidad_metrologica import AnalizadorMetrologicoService


class IngestarTelemetriaUseCase:
    """Caso de uso de orquestación de ingesta y normalización de telemetría MQTT."""

    _ultimas_persistencias: ClassVar[dict[str, datetime]] = {}
    _device_cache: ClassVar[dict[str, Dispositivo]] = ResolvedorDispositivoIngesta._device_cache
    _ultimos_heartbeats: ClassVar[dict[str, datetime]] = ResolvedorDispositivoIngesta._ultimos_heartbeats
    _filtro_persistencia: ClassVar[FiltroPersistenciaTemporalService] = ProcesadorAlertasIngesta._filtro_persistencia
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(
        self,
        repo_dispositivos: RepositorioDispositivosPort,
        repo_telemetria: RepositorioTelemetriaPort,
        publicador: PublicadorEventosPort | None = None,
        logger: LoggerPort | None = None,
        granularidad_segundos: int = 300,
        permitir_auto_registro: bool = True,
        disponibilidad_use_case: GestionarDisponibilidadUseCase | None = None,
        capturador_campana: CapturadorCampanaIngesta | None = None,
    ):
        self.repo_dispositivos = repo_dispositivos
        self.repo_telemetria = repo_telemetria
        self.publicador = publicador
        self.logger = logger
        self.granularidad_segundos = granularidad_segundos
        self.permitir_auto_registro = permitir_auto_registro
        self.disponibilidad_use_case = disponibilidad_use_case
        self.capturador_campana = capturador_campana

    def _parse_timestamp(self, ts_val: Any) -> datetime:
        return TelemetriaPayloadParser.parse_timestamp(ts_val)

    def _parse_fase(self, data: Any, suffix: str = "") -> MedicionFase:
        return TelemetriaPayloadParser.parse_fase(data, suffix=suffix)

    def _obtener_o_crear_dispositivo(
        self, mac_raw: str, dev_info: dict[str, Any] | None = None, ahora: datetime | None = None
    ) -> Dispositivo | None:
        return ResolvedorDispositivoIngesta.obtener_o_crear_dispositivo(
            mac_raw=mac_raw,
            dev_info=dev_info,
            ahora=ahora,
            repo_dispositivos=self.repo_dispositivos,
            permitir_auto_registro=self.permitir_auto_registro,
            logger=self.logger,
        )

    def _auto_resolver_alertas_si_corresponde(
        self,
        dispositivo_id: str,
        mac_raw: str,
        tipos_alerta: list[str],
        recorded_at: datetime,
    ) -> None:
        ProcesadorAlertasIngesta._auto_resolver_alertas(
            dispositivo_id=dispositivo_id,
            mac_raw=mac_raw,
            tipos_alerta=tipos_alerta,
            recorded_at=recorded_at,
            repo_telemetria=self.repo_telemetria,
            publicador=self.publicador,
            logger=self.logger,
        )

    def ejecutar(self, topico: str, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return

        partes = topico.split("/")
        if len(partes) < 4:
            return

        mac_raw = partes[2]
        subtopico = partes[3]

        if subtopico == "conf" and len(partes) >= 5 and partes[4] == "com":
            # Eco del propio comando saliente del backend (el broker reenvía al backend
            # sus propias publicaciones en un tópico al que también está suscripto).
            # No es actividad genuina del dispositivo: no marcar online ni retransmitir.
            if self.logger:
                self.logger.debug("mqtt_eco_comando_propio_ignorado", topico=topico)
            return

        if self.publicador and subtopico != "inst":
            self.publicador.publicar_telemetria_en_vivo(topico, payload)

        dev_info = payload.get("device_info") if isinstance(payload.get("device_info"), dict) else None
        recorded_at = self._parse_timestamp(payload.get("timestamp") or payload.get("t") or payload.get("time"))
        dispositivo = self._obtener_o_crear_dispositivo(mac_raw, dev_info, ahora=recorded_at)
        if dispositivo is None:
            return

        if subtopico == "inst":
            self._procesar_instantanea(topico, mac_raw, payload, dispositivo, recorded_at)
        elif subtopico in ("acc", "energyio"):
            self._procesar_energia(payload, dispositivo, recorded_at, fuente=subtopico)
        elif subtopico == "status":
            self._procesar_status(payload, dispositivo, recorded_at)
        elif subtopico == "event":
            self._procesar_event(payload, dispositivo)

    def _procesar_instantanea(
        self,
        topico: str,
        mac_raw: str,
        payload: dict[str, Any],
        dispositivo: Dispositivo,
        recorded_at: datetime,
    ) -> None:
        lectura = TelemetriaPayloadParser.parsear_instantanea(payload, dispositivo, recorded_at)

        if self.publicador:
            self.publicador.publicar_telemetria_en_vivo(
                topico,
                TelemetriaMapper.instantanea_to_dto(lectura, dispositivo=dispositivo).model_dump(mode="json"),
            )

        p_tot = lectura.potencia_activa_total.vatios if lectura.potencia_activa_total else None
        if self.disponibilidad_use_case is not None and p_tot is not None:
            self.disponibilidad_use_case.clasificar_lectura(dispositivo.id, float(p_tot), recorded_at)

        # Sumidero paralelo: si hay una campaña abierta, esta lectura se guarda a caudal
        # completo en `campaign_samples`. No altera el downsampling de más abajo, que
        # sigue decidiendo por su cuenta qué va a la serie permanente.
        if self.capturador_campana is not None:
            self.capturador_campana.capturar(dispositivo.id, lectura)

        ProcesadorAlertasIngesta.procesar_alertas(
            dispositivo=dispositivo,
            mac_raw=mac_raw,
            lectura=lectura,
            recorded_at=recorded_at,
            repo_telemetria=self.repo_telemetria,
            publicador=self.publicador,
            logger=self.logger,
        )

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
            # Capa 1: Validar coherencia fasorial
            self._validar_coherencia_instantanea(lectura, dispositivo.id, recorded_at)

        if self.logger:
            fp_tot = lectura.factor_potencia_total.valor if lectura.factor_potencia_total else None
            self.logger.info(
                "telemetria_instantanea_procesada",
                device_uid=dispositivo.device_uid.valor,
                p_activa_W=float(p_tot) if p_tot is not None else None,
                fp=float(fp_tot) if fp_tot is not None else None,
                persistido_db=debe_persistir,
            )

    def _procesar_energia(
        self,
        payload: dict[str, Any],
        dispositivo: Dispositivo,
        recorded_at: datetime,
        fuente: str,
    ) -> None:
        fases_con_ti = AnalizadorMetrologicoService.fases_con_ti_como_lista(
            getattr(dispositivo, "fases_con_ti", "R,S,T")
        )
        acumulado = TelemetriaPayloadParser.parsear_acumulado(
            payload,
            dispositivo.id,
            recorded_at,
            fases_con_ti=fases_con_ti,
            fuente=fuente,
            orden_fases=getattr(dispositivo, "orden_fases", None),
            invertido=getattr(dispositivo, "invertido", False),
        )

        # WP3 (D5, nivel ③): el medidor publica acumulados cada ~2 s, pero para
        # energía diaria/mensual solo importa el último valor de cada ventana —
        # el mismo throttle que ya usa _procesar_instantanea. La clave incluye
        # `fuente`: acc y energyio tienen ventanas independientes, si no, el que
        # llega primero en la ventana "gana el turno" y descarta al otro aunque
        # sea el prioritario (D1) el que quedó afuera — la prioridad la resuelve
        # guardar_energia en el momento en que SÍ llega a persistir, no acá.
        debe_persistir = True
        clave_throttle = f"{dispositivo.id}:energia:{fuente}"
        if self.granularidad_segundos > 0:
            with self._lock:
                ultima = self._ultimas_persistencias.get(clave_throttle)
                if ultima is not None and (recorded_at - ultima).total_seconds() < self.granularidad_segundos:
                    debe_persistir = False

        if debe_persistir:
            # D1: energyio (registro total del equipo) prioriza sobre acc (suma de
            # fases, respaldo) cuando ambos publican el mismo instante.
            self.repo_telemetria.guardar_energia(acumulado, prioritario=(fuente == "energyio"))
            with self._lock:
                self._ultimas_persistencias[clave_throttle] = recorded_at

        if self.logger:
            e_act = acumulado.energia_activa_neta.kwh if acumulado.energia_activa_neta else None
            self.logger.debug(
                "telemetria_energia_procesada",
                device_uid=dispositivo.device_uid.valor,
                kwh=float(e_act) if e_act is not None else None,
                persistido_db=debe_persistir,
            )

    def _procesar_status(
        self,
        payload: dict[str, Any],
        dispositivo: Dispositivo,
        recorded_at: datetime,
    ) -> None:
        log = TelemetriaPayloadParser.parsear_log_estado(payload, dispositivo.id, recorded_at)
        self.repo_telemetria.guardar_log_estado(log)
        ProcesadorAlertasIngesta.evaluar_conectividad(
            dispositivo=dispositivo,
            mac_raw=dispositivo.device_uid.valor,
            payload=payload,
            recorded_at=recorded_at,
            repo_telemetria=self.repo_telemetria,
            publicador=self.publicador,
            logger=self.logger,
        )

    def _procesar_event(
        self,
        payload: dict[str, Any],
        dispositivo: Dispositivo,
    ) -> None:
        alerta = TelemetriaPayloadParser.parsear_alerta_evento(payload, dispositivo.id)
        self.repo_telemetria.guardar_alerta(alerta)

    def _validar_coherencia_instantanea(
        self,
        lectura: Any,
        dispositivo_id: str,
        recorded_at: datetime,
    ) -> None:
        """Capa 1: Valida coherencia fasorial. Flag si error_s > 15%."""
        try:
            errores = []
            for fase in ["r", "s", "t"]:
                p = getattr(lectura, f"potencia_activa_{fase}", None)
                q = getattr(lectura, f"potencia_reactiva_{fase}", None)
                s = getattr(lectura, f"potencia_aparente_{fase}", None)

                if p is None or q is None or s is None:
                    continue

                p_val = float(p.vatios) if hasattr(p, "vatios") else float(p)
                q_val = float(q.var) if hasattr(q, "var") else float(q)
                s_val = float(s.va) if hasattr(s, "va") else float(s)

                s_teorica = math.sqrt(p_val**2 + q_val**2)
                if s_teorica > 0:
                    error_pct = 100.0 * abs(s_val - s_teorica) / s_teorica
                    errores.append(error_pct)

            if errores:
                max_error = max(errores)
                if max_error > 15.0:  # Umbral: 15%
                    if self.logger:
                        self.logger.warning(
                            "coherencia_baja_detectada",
                            device_id=dispositivo_id,
                            error_s_pct=round(max_error, 2),
                            recorded_at=recorded_at.isoformat(),
                        )
        except Exception as e:
            if self.logger:
                self.logger.error("error_validar_coherencia", error=str(e))


__all__ = [
    "IngestarTelemetriaUseCase",
    "acotar_payload_bruto",
    "parse_fase",
    "parse_timestamp",
    "sanear_entero",
    "sanear_ip",
]

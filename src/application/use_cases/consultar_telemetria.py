"""src/application/use_cases/consultar_telemetria.py."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.application.dtos.telemetria_dto import (
    AcumuladoEnergiaDTO,
    DiagnosticoFasesDispositivoDTO,
    EnergiaAgregadaDTO,
    HistoricoInstantaneasDTO,
    LecturaInstantaneaDTO,
    TelemetriaLatestResponseDTO,
)
from src.application.mappers.telemetria_mapper import TelemetriaMapper
from src.domain.telemetria.entities import Dispositivo, Suscripcion
from src.domain.telemetria.exceptions import (
    DispositivoNoEncontradoError,
    GranularidadEnergiaInvalidaError,
    ZonaHorariaInvalidaError,
)
from src.domain.telemetria.ports import (
    BufferTelemetriaEnVivoPort,
    RepositorioDispositivosPort,
    RepositorioOrganizacionesPort,
    RepositorioPlanesPort,
    RepositorioSuscripcionesPort,
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.services import (
    AgregacionEnergiaService,
    AnalizadorCalidadEnergiaService,
    PoliticaRetencionService,
    PoliticaSuscripcionService,
)
from src.domain.telemetria.value_objects import GranularidadEnergia, MacAddress, ModoFreeTier

# Throttle de persistencia de `IngestarTelemetriaUseCase` (granularidad_segundos por defecto).
_THROTTLE_PERSISTENCIA_SEGUNDOS = 300


class ConsultarTelemetriaUseCase:
    def __init__(
        self,
        repo_telemetria: RepositorioTelemetriaPort,
        repo_dispositivos: RepositorioDispositivosPort,
        repo_organizaciones: RepositorioOrganizacionesPort | None = None,
        repo_planes: RepositorioPlanesPort | None = None,
        buffer_en_vivo: BufferTelemetriaEnVivoPort | None = None,
        repo_suscripciones: RepositorioSuscripcionesPort | None = None,
        billing_habilitado: bool = True,
    ):
        self.repo_telemetria = repo_telemetria
        self.repo_dispositivos = repo_dispositivos
        self.repo_organizaciones = repo_organizaciones
        self.repo_planes = repo_planes
        self.buffer_en_vivo = buffer_en_vivo
        self.repo_suscripciones = repo_suscripciones
        self.billing_habilitado = billing_habilitado

    def _suscripcion_de_dispositivo(self, dev: Dispositivo) -> Suscripcion | None:
        """Suscripción de la organización del dispositivo; None si no se puede resolver la organización."""
        if not self.repo_organizaciones or not dev.planta_id:
            return None
        planta = self.repo_organizaciones.obtener_planta_por_id(dev.planta_id)
        if not planta or not planta.organizacion_id:
            return None
        if self.repo_organizaciones.obtener_por_id(planta.organizacion_id) is None:
            return None
        sus = (
            self.repo_suscripciones.obtener_por_organizacion(planta.organizacion_id)
            if self.repo_suscripciones
            else None
        )
        return sus or Suscripcion.por_defecto(planta.organizacion_id)

    def _resolver_dispositivo(self, id_o_uid: str) -> Dispositivo:
        # Check by UUID first
        dev = self.repo_dispositivos.obtener_por_id(id_o_uid)
        if dev:
            return dev
        # Try checking by MAC
        try:
            mac_vo = MacAddress(id_o_uid)
            dev = self.repo_dispositivos.obtener_por_uid(mac_vo)
            if dev:
                return dev
        except Exception:
            pass
        raise DispositivoNoEncontradoError(f"Dispositivo '{id_o_uid}' no encontrado.")

    def _obtener_contexto_suscripcion(self, dev: Dispositivo) -> tuple[bool, ModoFreeTier, int | None, int]:
        ahora = datetime.now(timezone.utc)
        sus = self._suscripcion_de_dispositivo(dev)

        if not self.billing_habilitado:
            # Cuando billing está deshabilitado, todos actúan como PRO ilimitado
            return True, ModoFreeTier.PRIVADO_BASICO, None, 0

        if sus is not None:
            # Obtener la organización para verificar si es cooperativa
            if self.repo_organizaciones and dev.planta_id:
                planta = self.repo_organizaciones.obtener_planta_por_id(dev.planta_id)
                if planta:
                    org = self.repo_organizaciones.obtener_por_id(planta.organizacion_id)
                    if org and org.es_cooperativa:
                        # Cooperativas: retención ilimitada, intervalo 0, sin restricciones
                        return True, ModoFreeTier.PRIVADO_BASICO, None, 0

            es_pro = PoliticaSuscripcionService.es_pro_vigente(sus.pro_vence_en, ahora)
            retencion_dias = PoliticaSuscripcionService.resolver_retencion_dias(es_pro, sus.modo_free)
            min_intervalo = PoliticaSuscripcionService.resolver_intervalo_minimo_segundos(es_pro, sus.modo_free)
            return es_pro, sus.modo_free, retencion_dias, min_intervalo
        # Dispositivos de desarrollo o sin asignación a planta no sufren restricciones
        return True, ModoFreeTier.PRIVADO_BASICO, 365, 0

    def _calcular_fecha_corte_retencion(self, dev: Dispositivo) -> datetime:
        ahora = datetime.now(timezone.utc)
        sus = self._suscripcion_de_dispositivo(dev)
        if sus is not None:
            if self.repo_planes and sus.plan_id:
                plan = self.repo_planes.obtener_por_id(sus.plan_id)
                if plan:
                    return PoliticaRetencionService.ventana_consulta(plan, ahora)
            es_pro = PoliticaSuscripcionService.es_pro_vigente(sus.pro_vence_en, ahora)
            dias = PoliticaSuscripcionService.resolver_retencion_dias(es_pro, sus.modo_free)
            # Si dias es None (retención ilimitada), retornar fecha muy antigua
            if dias is None:
                return datetime(1900, 1, 1, tzinfo=timezone.utc)
            return ahora - timedelta(days=dias)
        return ahora - timedelta(days=14)

    def _acotar_fecha_desde(self, dev: Dispositivo, desde: datetime | None) -> datetime:
        corte = self._calcular_fecha_corte_retencion(dev)
        if desde is None:
            return corte
        d_norm = desde if desde.tzinfo is not None else desde.replace(tzinfo=timezone.utc)
        c_norm = corte if corte.tzinfo is not None else corte.replace(tzinfo=timezone.utc)
        return max(d_norm, c_norm)

    @staticmethod
    def _resolver_intervalo_segundos(granularidad: str, horas: int | None) -> int:
        g = (granularidad or "raw").strip().lower()
        if g == "raw":
            return 0
        if g in ("1m", "1min", "60s"):
            return 60
        if g in ("5m", "5min", "300s"):
            return 300
        if g in ("15m", "15min", "900s"):
            return 900
        if g in ("1h", "60m", "3600s"):
            return 3600
        if g == "auto":
            h = horas if horas is not None else 24
            if h <= 2:
                return 60
            elif h <= 24:
                return 300
            else:
                return 900
        return 0

    def obtener_ultima_telemetria(self, id_o_uid: str) -> TelemetriaLatestResponseDTO:
        dev = self._resolver_dispositivo(id_o_uid)
        inst = self.repo_telemetria.obtener_ultima_instantanea(dev.id)
        acc = self.repo_telemetria.obtener_ultimo_acumulado(dev.id)
        inst_dto = TelemetriaMapper.instantanea_to_dto(inst, dispositivo=dev) if inst else None

        return TelemetriaLatestResponseDTO(
            device_id=dev.id,
            instantanea=inst_dto,
            energia=TelemetriaMapper.acumulado_to_dto(acc) if acc else None,
            analitica=inst_dto.analitica if inst_dto else None,
        )

    def datos_desde(self, id_o_uid: str) -> datetime:
        """Fecha más antigua consultable del dispositivo (corte de retención de su plan)."""
        return self._calcular_fecha_corte_retencion(self._resolver_dispositivo(id_o_uid))

    def historico_instantaneas(
        self,
        id_o_uid: str,
        limite: int = 100,
        desde: datetime | None = None,
        granularidad: str = "raw",
        horas: int | None = None,
        hasta: datetime | None = None,
    ) -> HistoricoInstantaneasDTO:
        lecturas = self.listar_instantaneas(id_o_uid, limite, desde, granularidad, horas, hasta)
        return HistoricoInstantaneasDTO(lecturas=lecturas, datos_desde=self.datos_desde(id_o_uid))

    def listar_instantaneas(
        self,
        id_o_uid: str,
        limite: int = 100,
        desde: datetime | None = None,
        granularidad: str = "raw",
        horas: int | None = None,
        hasta: datetime | None = None,
    ) -> list[LecturaInstantaneaDTO]:
        dev = self._resolver_dispositivo(id_o_uid)
        _, _, _, min_intervalo = self._obtener_contexto_suscripcion(dev)
        es_monofasico = AnalizadorCalidadEnergiaService.es_instalacion_monofasica(
            getattr(dev, "tipo_instalacion", "CONSUMO"),
            getattr(dev, "fases_con_ti", "R,S,T"),
        )

        fin_ventana = hasta or datetime.now(timezone.utc)
        horas_efectivas = horas
        if horas_efectivas is None and desde is not None:
            horas_efectivas = max(1, int((fin_ventana - desde).total_seconds() / 3600.0))

        es_lttb = (granularidad or "").strip().lower() == "lttb"
        intervalo_pedido = self._resolver_intervalo_segundos(granularidad, horas_efectivas)
        intervalo_segundos = max(intervalo_pedido, min_intervalo)
        desde_efectivo = self._acotar_fecha_desde(dev, desde)
        if hasta is not None and hasta < desde_efectivo:
            # Ventana entera antes del corte de retención: vacía, no error (D3).
            return []

        limite_db = max(limite * 10, 5000) if (intervalo_segundos > 0 or es_lttb) else limite
        lecturas = self.repo_telemetria.listar_instantaneas(dev.id, limite_db, desde_efectivo, hasta)

        if es_lttb:
            lecturas = AnalizadorCalidadEnergiaService.downsample_lttb(lecturas, target_points=limite)
        elif intervalo_segundos > 0:
            lecturas = AnalizadorCalidadEnergiaService.agregar_lecturas_en_intervalo(
                lecturas, intervalo_segundos, es_monofasico=es_monofasico
            )[:limite]
        else:
            lecturas = lecturas[:limite]

        lecturas_dto = [TelemetriaMapper.instantanea_to_dto(item, dispositivo=dev) for item in lecturas]
        if not self._buffer_aplica(hasta, intervalo_segundos):
            return lecturas_dto
        return self._mezclar_buffer_en_vivo(dev.id, lecturas_dto, limite, hasta)

    @staticmethod
    def _buffer_aplica(hasta: datetime | None, intervalo_segundos: int) -> bool:
        """D4: el buffer en vivo solo tiene lecturas aún no persistidas (throttle de 300 s), así
        que solo aporta si la ventana termina en el presente o dentro del último intervalo."""
        if hasta is None:
            return True
        margen = timedelta(seconds=max(intervalo_segundos, _THROTTLE_PERSISTENCIA_SEGUNDOS))
        return hasta >= datetime.now(timezone.utc) - margen

    def _mezclar_buffer_en_vivo(
        self,
        dispositivo_id: str,
        lecturas_dto: list[LecturaInstantaneaDTO],
        limite: int,
        hasta: datetime | None = None,
    ) -> list[LecturaInstantaneaDTO]:
        """Antepone al histórico de BD las lecturas recibidas en vivo que todavía no bajaron
        a la base de datos (downsampling de persistencia), para que un F5 del navegador no
        pierda continuidad mientras el buffer en RAM del backend siga vivo."""
        if not self.buffer_en_vivo:
            return lecturas_dto

        vistos = {dto.registrado_en for dto in lecturas_dto}
        candidatos = [
            LecturaInstantaneaDTO.model_validate(dato) for dato in self.buffer_en_vivo.obtener(dispositivo_id)
        ]
        recientes = [
            dto
            for dto in candidatos
            if dto.registrado_en not in vistos and (hasta is None or dto.registrado_en <= hasta)
        ]
        recientes.sort(key=lambda dto: dto.registrado_en, reverse=True)
        return (recientes + lecturas_dto)[:limite]

    def listar_energias(
        self, id_o_uid: str, limite: int = 100, desde: datetime | None = None
    ) -> list[AcumuladoEnergiaDTO]:
        dev = self._resolver_dispositivo(id_o_uid)
        desde_efectivo = self._acotar_fecha_desde(dev, desde)
        acumulados = self.repo_telemetria.listar_energias(dev.id, limite, desde_efectivo)
        return [TelemetriaMapper.acumulado_to_dto(a) for a in acumulados]

    def listar_energia_agregada(
        self,
        id_o_uid: str,
        granularidad: str = "day",
        zona: str = "America/Argentina/Buenos_Aires",
        dias: int | None = None,
    ) -> list[EnergiaAgregadaDTO]:
        dev = self._resolver_dispositivo(id_o_uid)

        try:
            granularidad_enum = GranularidadEnergia(granularidad)
        except ValueError as exc:
            raise GranularidadEnergiaInvalidaError(f"Granularidad inválida: {granularidad}") from exc

        try:
            zona_info = ZoneInfo(zona)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ZonaHorariaInvalidaError(f"Zona horaria inválida: {zona}") from exc

        desde = datetime.now(timezone.utc) - timedelta(days=dias) if dias else None
        desde_efectivo = self._acotar_fecha_desde(dev, desde)
        acumulados = self.repo_telemetria.listar_ultimos_acumulados_por_periodo(
            dev.id, desde_efectivo, granularidad=granularidad_enum.value, zona=zona
        )
        agregados = AgregacionEnergiaService.agregar_por_periodo(acumulados, granularidad_enum, zona_info)
        return [TelemetriaMapper.energia_agregada_to_dto(a) for a in agregados]

    def diagnosticar_fases(self, id_o_uid: str) -> DiagnosticoFasesDispositivoDTO:
        from src.domain.telemetria.servicios.analizador_fasorial import AnalizadorFasorialService

        dev = self._resolver_dispositivo(id_o_uid)
        lectura = self.repo_telemetria.obtener_ultima_instantanea(dev.id)
        if lectura is None:
            from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase

            lectura = LecturaInstantanea(
                id=None,
                dispositivo_id=dev.id,
                registrado_en=datetime.now(timezone.utc),
                fase_r=MedicionFase(),
                fase_s=MedicionFase(),
                fase_t=MedicionFase(),
            )

        fases_ti = (
            [f.strip().upper() for f in dev.fases_con_ti.split(",")] if getattr(dev, "fases_con_ti", None) else None
        )
        diag = AnalizadorFasorialService.diagnosticar_lectura(dev.id, lectura, fases_con_ti=fases_ti)
        return TelemetriaMapper.diagnostico_fasorial_to_dto(diag)

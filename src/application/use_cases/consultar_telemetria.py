"""src/application/use_cases/consultar_telemetria.py."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.application.dtos.telemetria_dto import (
    AcumuladoEnergiaDTO,
    DiagnosticoFasesDispositivoDTO,
    EnergiaAgregadaDTO,
    LecturaInstantaneaDTO,
    TelemetriaLatestResponseDTO,
)
from src.application.mappers.telemetria_mapper import TelemetriaMapper
from src.domain.telemetria.entities import Dispositivo
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
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.services import (
    AgregacionEnergiaService,
    AnalizadorCalidadEnergiaService,
    PoliticaRetencionService,
    PoliticaSuscripcionService,
)
from src.domain.telemetria.value_objects import GranularidadEnergia, MacAddress, ModoFreeTier


class ConsultarTelemetriaUseCase:
    def __init__(
        self,
        repo_telemetria: RepositorioTelemetriaPort,
        repo_dispositivos: RepositorioDispositivosPort,
        repo_organizaciones: RepositorioOrganizacionesPort | None = None,
        repo_planes: RepositorioPlanesPort | None = None,
        buffer_en_vivo: BufferTelemetriaEnVivoPort | None = None,
    ):
        self.repo_telemetria = repo_telemetria
        self.repo_dispositivos = repo_dispositivos
        self.repo_organizaciones = repo_organizaciones
        self.repo_planes = repo_planes
        self.buffer_en_vivo = buffer_en_vivo

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

    def _obtener_contexto_suscripcion(self, dev: Dispositivo) -> tuple[bool, ModoFreeTier, int, int]:
        ahora = datetime.now(timezone.utc)
        if self.repo_organizaciones and dev.planta_id:
            planta = self.repo_organizaciones.obtener_planta_por_id(dev.planta_id)
            if planta and planta.organizacion_id:
                org = self.repo_organizaciones.obtener_por_id(planta.organizacion_id)
                if org:
                    es_pro = PoliticaSuscripcionService.es_pro_vigente(org.pro_vence_en, ahora)
                    retencion_dias = PoliticaSuscripcionService.resolver_retencion_dias(es_pro, org.modo_free)
                    min_intervalo = PoliticaSuscripcionService.resolver_intervalo_minimo_segundos(es_pro, org.modo_free)
                    return es_pro, org.modo_free, retencion_dias, min_intervalo
        # Dispositivos de desarrollo o sin asignación a planta no sufren restricciones
        return True, ModoFreeTier.PRIVADO_BASICO, 365, 0

    def _calcular_fecha_corte_retencion(self, dev: Dispositivo) -> datetime:
        ahora = datetime.now(timezone.utc)
        if self.repo_organizaciones and dev.planta_id:
            planta = self.repo_organizaciones.obtener_planta_por_id(dev.planta_id)
            if planta and planta.organizacion_id:
                org = self.repo_organizaciones.obtener_por_id(planta.organizacion_id)
                if org and self.repo_planes and org.plan_id:
                    plan = self.repo_planes.obtener_por_id(org.plan_id)
                    if plan:
                        return PoliticaRetencionService.ventana_consulta(plan, ahora)
                if org:
                    es_pro = PoliticaSuscripcionService.es_pro_vigente(org.pro_vence_en, ahora)
                    dias = PoliticaSuscripcionService.resolver_retencion_dias(es_pro, org.modo_free)
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
        inst_dto = TelemetriaMapper.instantanea_to_dto(inst) if inst else None

        return TelemetriaLatestResponseDTO(
            device_id=dev.id,
            instantanea=inst_dto,
            energia=TelemetriaMapper.acumulado_to_dto(acc) if acc else None,
            analitica=inst_dto.analitica if inst_dto else None,
        )

    def listar_instantaneas(
        self,
        id_o_uid: str,
        limite: int = 100,
        desde: datetime | None = None,
        granularidad: str = "raw",
        horas: int | None = None,
    ) -> list[LecturaInstantaneaDTO]:
        dev = self._resolver_dispositivo(id_o_uid)
        _, _, _, min_intervalo = self._obtener_contexto_suscripcion(dev)
        es_monofasico = AnalizadorCalidadEnergiaService.es_instalacion_monofasica(
            getattr(dev, "tipo_instalacion", "CONSUMO"),
            getattr(dev, "fases_con_ti", "R,S,T"),
        )

        ahora = datetime.now(timezone.utc)
        horas_efectivas = horas
        if horas_efectivas is None and desde is not None:
            horas_efectivas = max(1, int((ahora - desde).total_seconds() / 3600.0))

        intervalo_pedido = self._resolver_intervalo_segundos(granularidad, horas_efectivas)
        intervalo_segundos = max(intervalo_pedido, min_intervalo)
        desde_efectivo = self._acotar_fecha_desde(dev, desde)

        limite_db = max(limite * 10, 5000) if intervalo_segundos > 0 else limite
        lecturas = self.repo_telemetria.listar_instantaneas(dev.id, limite_db, desde_efectivo)

        if intervalo_segundos > 0:
            lecturas = AnalizadorCalidadEnergiaService.agregar_lecturas_en_intervalo(
                lecturas, intervalo_segundos, es_monofasico=es_monofasico
            )[:limite]
        else:
            lecturas = lecturas[:limite]

        lecturas_dto = [TelemetriaMapper.instantanea_to_dto(item) for item in lecturas]
        return self._mezclar_buffer_en_vivo(dev.id, lecturas_dto, limite)

    def _mezclar_buffer_en_vivo(
        self, dispositivo_id: str, lecturas_dto: list[LecturaInstantaneaDTO], limite: int
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
        recientes = [dto for dto in candidatos if dto.registrado_en not in vistos]
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
        acumulados = self.repo_telemetria.listar_acumulados_para_agregacion(dev.id, desde_efectivo)
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

        diag = AnalizadorFasorialService.diagnosticar_lectura(dev.id, lectura)
        return TelemetriaMapper.diagnostico_fasorial_to_dto(diag)

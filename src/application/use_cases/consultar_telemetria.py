from datetime import datetime, timezone

from src.application.dtos.telemetria_dto import (
    AcumuladoEnergiaDTO,
    LecturaInstantaneaDTO,
    TelemetriaLatestResponseDTO,
)
from src.application.mappers.telemetria_mapper import TelemetriaMapper
from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.exceptions import DispositivoNoEncontradoError
from src.domain.telemetria.ports import (
    RepositorioDispositivosPort,
    RepositorioOrganizacionesPort,
    RepositorioPlanesPort,
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.services import (
    AnalizadorCalidadEnergiaService,
    PoliticaRetencionService,
)
from src.domain.telemetria.value_objects import MacAddress


class ConsultarTelemetriaUseCase:
    def __init__(
        self,
        repo_telemetria: RepositorioTelemetriaPort,
        repo_dispositivos: RepositorioDispositivosPort,
        repo_organizaciones: RepositorioOrganizacionesPort | None = None,
        repo_planes: RepositorioPlanesPort | None = None,
    ):
        self.repo_telemetria = repo_telemetria
        self.repo_dispositivos = repo_dispositivos
        self.repo_organizaciones = repo_organizaciones
        self.repo_planes = repo_planes

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

    def _calcular_fecha_corte_retencion(self, dev: Dispositivo) -> datetime:
        ahora = datetime.now(timezone.utc)
        if self.repo_organizaciones and self.repo_planes and dev.planta_id:
            planta = self.repo_organizaciones.obtener_planta_por_id(dev.planta_id)
            if planta and planta.organizacion_id:
                org = self.repo_organizaciones.obtener_por_id(planta.organizacion_id)
                if org and org.plan_id:
                    plan = self.repo_planes.obtener_por_id(org.plan_id)
                    if plan:
                        return PoliticaRetencionService.ventana_consulta(plan, ahora)
        # Fallback Plan 0: 7 días de retención
        from datetime import timedelta

        return ahora - timedelta(days=7)

    def _acotar_fecha_desde(self, dev: Dispositivo, desde: datetime | None) -> datetime:
        corte = self._calcular_fecha_corte_retencion(dev)
        if desde is None:
            return corte
        # Si el cliente pide desde una fecha más vieja que la retención permitida, acotamos
        return max(desde, corte)

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

        return TelemetriaLatestResponseDTO(
            device_id=dev.id,
            instantanea=TelemetriaMapper.instantanea_to_dto(inst) if inst else None,
            energia=TelemetriaMapper.acumulado_to_dto(acc) if acc else None,
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

        ahora = datetime.now(timezone.utc)
        horas_efectivas = horas
        if horas_efectivas is None and desde is not None:
            horas_efectivas = max(1, int((ahora - desde).total_seconds() / 3600.0))

        intervalo_segundos = self._resolver_intervalo_segundos(granularidad, horas_efectivas)
        desde_efectivo = self._acotar_fecha_desde(dev, desde)

        limite_db = max(limite * 10, 5000) if intervalo_segundos > 0 else limite
        lecturas = self.repo_telemetria.listar_instantaneas(dev.id, limite_db, desde_efectivo)

        if intervalo_segundos > 0:
            lecturas = AnalizadorCalidadEnergiaService.agregar_lecturas_en_intervalo(lecturas, intervalo_segundos)[
                :limite
            ]
        else:
            lecturas = lecturas[:limite]

        return [TelemetriaMapper.instantanea_to_dto(item) for item in lecturas]

    def listar_energias(
        self, id_o_uid: str, limite: int = 100, desde: datetime | None = None
    ) -> list[AcumuladoEnergiaDTO]:
        dev = self._resolver_dispositivo(id_o_uid)
        desde_efectivo = self._acotar_fecha_desde(dev, desde)
        acumulados = self.repo_telemetria.listar_energias(dev.id, limite, desde_efectivo)
        return [TelemetriaMapper.acumulado_to_dto(a) for a in acumulados]

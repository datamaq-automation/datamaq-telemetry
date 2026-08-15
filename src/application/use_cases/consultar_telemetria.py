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
from src.domain.telemetria.services import PoliticaRetencionService
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
        self, id_o_uid: str, limite: int = 100, desde: datetime | None = None
    ) -> list[LecturaInstantaneaDTO]:
        dev = self._resolver_dispositivo(id_o_uid)
        desde_efectivo = self._acotar_fecha_desde(dev, desde)
        lecturas = self.repo_telemetria.listar_instantaneas(dev.id, limite, desde_efectivo)
        return [TelemetriaMapper.instantanea_to_dto(item) for item in lecturas]

    def listar_energias(
        self, id_o_uid: str, limite: int = 100, desde: datetime | None = None
    ) -> list[AcumuladoEnergiaDTO]:
        dev = self._resolver_dispositivo(id_o_uid)
        desde_efectivo = self._acotar_fecha_desde(dev, desde)
        acumulados = self.repo_telemetria.listar_energias(dev.id, limite, desde_efectivo)
        return [TelemetriaMapper.acumulado_to_dto(a) for a in acumulados]

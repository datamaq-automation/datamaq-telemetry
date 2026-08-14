from datetime import datetime

from src.application.dtos.telemetria_dto import (
    AcumuladoEnergiaDTO,
    LecturaInstantaneaDTO,
    TelemetriaLatestResponseDTO,
)
from src.application.mappers.telemetria_mapper import TelemetriaMapper
from src.domain.telemetria.exceptions import DispositivoNoEncontradoError
from src.domain.telemetria.ports import (
    RepositorioDispositivosPort,
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.value_objects import MacAddress


class ConsultarTelemetriaUseCase:
    def __init__(
        self,
        repo_telemetria: RepositorioTelemetriaPort,
        repo_dispositivos: RepositorioDispositivosPort,
    ):
        self.repo_telemetria = repo_telemetria
        self.repo_dispositivos = repo_dispositivos

    def _resolver_dispositivo_id(self, id_o_uid: str) -> str:
        # Check by UUID first
        dev = self.repo_dispositivos.obtener_por_id(id_o_uid)
        if dev:
            return dev.id
        # Try checking by MAC
        try:
            mac_vo = MacAddress(id_o_uid)
            dev = self.repo_dispositivos.obtener_por_uid(mac_vo)
            if dev:
                return dev.id
        except Exception:
            pass
        raise DispositivoNoEncontradoError(f"Dispositivo '{id_o_uid}' no encontrado.")

    def obtener_ultima_telemetria(self, id_o_uid: str) -> TelemetriaLatestResponseDTO:
        dispositivo_id = self._resolver_dispositivo_id(id_o_uid)
        inst = self.repo_telemetria.obtener_ultima_instantanea(dispositivo_id)
        acc = self.repo_telemetria.obtener_ultimo_acumulado(dispositivo_id)

        return TelemetriaLatestResponseDTO(
            device_id=dispositivo_id,
            instantanea=TelemetriaMapper.instantanea_to_dto(inst) if inst else None,
            energia=TelemetriaMapper.acumulado_to_dto(acc) if acc else None,
        )

    def listar_instantaneas(
        self, id_o_uid: str, limite: int = 100, desde: datetime | None = None
    ) -> list[LecturaInstantaneaDTO]:
        dispositivo_id = self._resolver_dispositivo_id(id_o_uid)
        lecturas = self.repo_telemetria.listar_instantaneas(dispositivo_id, limite, desde)
        return [TelemetriaMapper.instantanea_to_dto(item) for item in lecturas]

    def listar_energias(
        self, id_o_uid: str, limite: int = 100, desde: datetime | None = None
    ) -> list[AcumuladoEnergiaDTO]:
        dispositivo_id = self._resolver_dispositivo_id(id_o_uid)
        acumulados = self.repo_telemetria.listar_energias(dispositivo_id, limite, desde)
        return [TelemetriaMapper.acumulado_to_dto(a) for a in acumulados]

from datetime import datetime, timezone

from src.application.dtos.alerta_dto import AlertaResponseDTO
from src.application.mappers.alerta_mapper import AlertaMapper
from src.domain.telemetria.exceptions import AlertaNoEncontradaError
from src.domain.telemetria.ports import RepositorioTelemetriaPort


class GestionarAlertasUseCase:
    def __init__(self, repo_telemetria: RepositorioTelemetriaPort):
        self.repo_telemetria = repo_telemetria

    def listar_alertas(
        self,
        dispositivo_id: str | None = None,
        solo_abiertas: bool = False,
        limite: int = 100,
    ) -> list[AlertaResponseDTO]:
        alertas = self.repo_telemetria.listar_alertas(
            dispositivo_id=dispositivo_id,
            solo_abiertas=solo_abiertas,
            limite=limite,
        )
        return [AlertaMapper.to_dto(a) for a in alertas]

    def resolver_alerta(self, alerta_id: int) -> AlertaResponseDTO:
        alerta = self.repo_telemetria.obtener_alerta_por_id(alerta_id)
        if not alerta:
            raise AlertaNoEncontradaError(f"Alerta con ID {alerta_id} no encontrada.")

        alerta.marcar_resuelta(datetime.now(timezone.utc))
        self.repo_telemetria.guardar_alerta(alerta)
        return AlertaMapper.to_dto(alerta)

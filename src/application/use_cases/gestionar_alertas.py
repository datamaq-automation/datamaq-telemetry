"""src/application/use_cases/gestionar_alertas.py."""
from datetime import datetime, timezone

from src.application.dtos.alerta_dto import AlertaResponseDTO
from src.application.mappers.alerta_mapper import AlertaMapper
from src.domain.telemetria.exceptions import AlertaNoEncontradaError
from src.domain.telemetria.ports import (
    PublicadorEventosPort,
    RepositorioDispositivosPort,
    RepositorioTelemetriaPort,
)


class GestionarAlertasUseCase:
    def __init__(
        self,
        repo_telemetria: RepositorioTelemetriaPort,
        publicador: PublicadorEventosPort | None = None,
        repo_dispositivos: RepositorioDispositivosPort | None = None,
    ):
        self.repo_telemetria = repo_telemetria
        self.publicador = publicador
        self.repo_dispositivos = repo_dispositivos

    def listar_alertas(
        self,
        dispositivo_id: str | None = None,
        solo_abiertas: bool = False,
        severidad: str | None = None,
        limite: int = 100,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> list[AlertaResponseDTO]:
        alertas = self.repo_telemetria.listar_alertas(
            dispositivo_id=dispositivo_id,
            solo_abiertas=solo_abiertas,
            severidad=severidad,
            limite=limite,
            desde=desde,
            hasta=hasta,
        )
        return [AlertaMapper.to_dto(a) for a in alertas]

    def resolver_alerta(self, alerta_id: int, observaciones: str | None = None) -> AlertaResponseDTO:
        alerta = self.repo_telemetria.obtener_alerta_por_id(alerta_id)
        if not alerta:
            raise AlertaNoEncontradaError(f"Alerta con ID {alerta_id} no encontrada.")

        alerta.marcar_resuelta(datetime.now(timezone.utc), observaciones=observaciones)
        self.repo_telemetria.guardar_alerta(alerta)

        # Difusión en vivo vía WebSocket hacia todas las consolas conectadas
        if self.publicador:
            mac_str = alerta.dispositivo_id
            if self.repo_dispositivos:
                dev = self.repo_dispositivos.obtener_por_id(alerta.dispositivo_id)
                if dev and dev.device_uid:
                    mac_str = dev.device_uid.valor.upper()
            self.publicador.publicar_telemetria_en_vivo(
                f"m/wifi/{mac_str}/alertas",
                AlertaMapper.to_dto(alerta).model_dump(mode="json"),
            )

        return AlertaMapper.to_dto(alerta)

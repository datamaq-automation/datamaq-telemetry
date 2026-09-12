"""src/application/use_cases/exportar_telemetria.py."""
from collections.abc import Generator
from datetime import datetime

from src.application.mappers.csv_streaming_mapper import CsvStreamingMapper
from src.domain.telemetria.ports import RepositorioDispositivosPort, RepositorioTelemetriaPort


class ExportarTelemetriaUseCase:
    """Caso de uso para la exportación en streaming O(1) de telemetría histórica a CSV."""

    def __init__(
        self,
        repo_telemetria: RepositorioTelemetriaPort,
        repo_dispositivos: RepositorioDispositivosPort | None = None,
    ):
        self.repo_telemetria = repo_telemetria
        self.repo_dispositivos = repo_dispositivos

    def ejecutar(
        self,
        dispositivo_id: str,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        limite: int = 10000,
    ) -> Generator[str, None, None]:
        iterador = self.repo_telemetria.iterar_instantaneas(
            dispositivo_id=dispositivo_id,
            desde=desde,
            hasta=hasta,
            limite=limite,
        )
        return CsvStreamingMapper.generar_csv_telemetria(iterador)

"""tests/unit/test_purga_data_lifecycle.py — Tests de ciclo de vida y purga (ISO 27001 A.8.10 & ISO 50001)."""

from datetime import datetime, timezone

from src.application.dtos.purga_dto import PurgaRequestDTO
from src.application.use_cases.purgar_telemetria import PurgarTelemetriaExpiradaUseCase
from tests.unit.test_optimizacion_db import MockTelemetriaRepo


class SpyRepoTelemetria(MockTelemetriaRepo):
    def __init__(self):
        super().__init__()
        self.corte_inst: datetime | None = None
        self.corte_energia: datetime | None = None
        self.corte_logs: datetime | None = None
        self.corte_alertas: datetime | None = None
        self.batch_size_inst: int | None = None

    def purgar_instantaneas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        self.corte_inst = fecha_limite
        self.batch_size_inst = batch_size
        return 0

    def purgar_energias_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        self.corte_energia = fecha_limite
        return 0

    def purgar_status_logs_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        self.corte_logs = fecha_limite
        return 0

    def purgar_alertas_resueltas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        self.corte_alertas = fecha_limite
        return 0


def test_purga_data_lifecycle_politica_por_defecto():
    repo = SpyRepoTelemetria()
    use_case = PurgarTelemetriaExpiradaUseCase(repo)

    dto = PurgaRequestDTO(batch_size=50000)
    ahora = datetime.now(timezone.utc)
    use_case.ejecutar(dto)

    assert repo.batch_size_inst == 50000

    # Crudo / Instantáneo: retención de 45 días
    assert repo.corte_inst is not None
    dias_inst = (ahora - repo.corte_inst).total_seconds() / 86400
    assert 44.9 <= dias_inst <= 45.1

    # Agregados de Energía: retención de 5 años (1825 días) para trazabilidad ISO 50001
    assert repo.corte_energia is not None
    dias_ene = (ahora - repo.corte_energia).total_seconds() / 86400
    assert 1824.9 <= dias_ene <= 1825.1


def test_purga_data_lifecycle_overrides_independientes():
    repo = SpyRepoTelemetria()
    use_case = PurgarTelemetriaExpiradaUseCase(repo)

    dto = PurgaRequestDTO(
        dias_retencion_instantaneas=30,
        dias_retencion_energia=365,
        batch_size=10000,
    )
    ahora = datetime.now(timezone.utc)
    use_case.ejecutar(dto)

    assert repo.batch_size_inst == 10000

    dias_inst = (ahora - repo.corte_inst).total_seconds() / 86400
    assert 29.9 <= dias_inst <= 30.1

    dias_ene = (ahora - repo.corte_energia).total_seconds() / 86400
    assert 364.9 <= dias_ene <= 365.1

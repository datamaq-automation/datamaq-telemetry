"""tests/unit/test_purga_rango.py — Purga de telemetría por rango temporal (corte_hasta)."""

from datetime import datetime, timedelta, timezone

import pytest

from scripts import purge_telemetry as pt
from src.application.dtos.purga_dto import PurgaRequestDTO
from src.application.use_cases.purgar_telemetria import PurgarTelemetriaExpiradaUseCase
from src.domain.telemetria.exceptions import DominioTelemetriaException
from tests.unit.test_optimizacion_db import MockTelemetriaRepo


class SpyTelemetriaRepo(MockTelemetriaRepo):
    """Registra las fechas límite enviadas a los métodos de purga."""

    def __init__(self) -> None:
        super().__init__()
        self.cortes_instantaneas: list[datetime] = []
        self.cortes_energias: list[datetime] = []
        self.cortes_logs: list[datetime] = []
        self.cortes_alertas: list[datetime] = []

    def purgar_instantaneas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        self.cortes_instantaneas.append(fecha_limite)
        return super().purgar_instantaneas_anteriores_a(fecha_limite, batch_size)

    def purgar_energias_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        self.cortes_energias.append(fecha_limite)
        return super().purgar_energias_anteriores_a(fecha_limite, batch_size)

    def purgar_status_logs_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        self.cortes_logs.append(fecha_limite)
        return super().purgar_status_logs_anteriores_a(fecha_limite, batch_size)

    def purgar_alertas_resueltas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        self.cortes_alertas.append(fecha_limite)
        return super().purgar_alertas_resueltas_anteriores_a(fecha_limite, batch_size)


CORTE = datetime(2026, 9, 1, 21, 40, 4, tzinfo=timezone.utc)


def test_purga_con_corte_hasta_usa_esa_fecha() -> None:
    repo = SpyTelemetriaRepo()
    use_case = PurgarTelemetriaExpiradaUseCase(repo)

    res = use_case.ejecutar(PurgaRequestDTO(corte_hasta=CORTE, batch_size=100))

    assert res.total_registros_eliminados == 0
    assert repo.cortes_instantaneas == [CORTE]
    assert repo.cortes_energias == [CORTE]
    assert repo.cortes_logs == [CORTE]
    assert repo.cortes_alertas == [CORTE]


def test_purga_sin_corte_hasta_conserva_retencion_por_dias() -> None:
    repo = SpyTelemetriaRepo()
    use_case = PurgarTelemetriaExpiradaUseCase(repo)

    use_case.ejecutar(PurgaRequestDTO(batch_size=100))

    ahora = datetime.now(timezone.utc)
    assert repo.cortes_instantaneas and all(c < ahora for c in repo.cortes_instantaneas)
    assert repo.cortes_logs and all(c < ahora for c in repo.cortes_logs)
    assert repo.cortes_alertas and all(c < ahora for c in repo.cortes_alertas)


def test_purga_corte_hasta_futuro_es_rechazado() -> None:
    repo = SpyTelemetriaRepo()
    use_case = PurgarTelemetriaExpiradaUseCase(repo)
    futuro = datetime.now(timezone.utc) + timedelta(days=1)

    with pytest.raises(DominioTelemetriaException):
        use_case.ejecutar(PurgaRequestDTO(corte_hasta=futuro, batch_size=100))


def test_parsear_corte_hasta_naive_asume_utc() -> None:
    assert pt.parsear_corte_hasta("2026-09-01 21:40:04") == CORTE


def test_parsear_corte_hasta_con_offset_utc() -> None:
    assert pt.parsear_corte_hasta("2026-09-01T21:40:04+00:00") == CORTE


def test_parsear_corte_hasta_formato_invalido() -> None:
    with pytest.raises(ValueError):
        pt.parsear_corte_hasta("no-es-una-fecha")

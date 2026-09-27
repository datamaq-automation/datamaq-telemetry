"""tests/integration/test_coherencia_dispositivos.py — Capa 2: Detección en Gauntlet (Diario)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.domain.telemetria.servicios.calculador_coherencia import CalculadorCoherenciaService


def test_calcular_coherencia_promedio_lista_vacia():
    """Promedio de lista vacía es 0.0."""
    resultado = CalculadorCoherenciaService.calcular_coherencia_promedio([])
    assert resultado == 0.0


def test_calcular_coherencia_promedio_valores():
    """Calcula media aritmética correctamente."""
    resultado = CalculadorCoherenciaService.calcular_coherencia_promedio([5.0, 10.0, 15.0])
    assert resultado == 10.0

    resultado = CalculadorCoherenciaService.calcular_coherencia_promedio([1.0, 2.0, 3.0, 4.0])
    assert resultado == 2.5


def test_evaluar_degradacion_no_degradado():
    """Cambio positivo pero < 20% → no está degradado."""
    está_degradado, pct = CalculadorCoherenciaService.evaluar_degradacion(12.0, 10.0)
    assert está_degradado is False
    assert pct == 20.0  # Límite exacto

    está_degradado, pct = CalculadorCoherenciaService.evaluar_degradacion(11.0, 10.0)
    assert está_degradado is False
    assert pct == 10.0


def test_evaluar_degradacion_si_degradado():
    """Cambio > 20% → está degradado."""
    está_degradado, pct = CalculadorCoherenciaService.evaluar_degradacion(12.1, 10.0)
    assert está_degradado is True
    assert pct == pytest.approx(21.0, abs=0.1)

    está_degradado, pct = CalculadorCoherenciaService.evaluar_degradacion(20.0, 10.0)
    assert está_degradado is True
    assert pct == 100.0


def test_evaluar_degradacion_mejora():
    """Cambio negativo → no está degradado (mejora)."""
    está_degradado, pct = CalculadorCoherenciaService.evaluar_degradacion(10.0, 15.0)
    assert está_degradado is False
    assert pct == pytest.approx(-33.33, abs=0.1)


def test_evaluar_degradacion_baseline_cero():
    """Baseline 0 con promedio_hoy > 0 → degradado."""
    está_degradado, pct = CalculadorCoherenciaService.evaluar_degradacion(5.0, 0.0)
    assert está_degradado is True
    assert pct == 100.0

    está_degradado, pct = CalculadorCoherenciaService.evaluar_degradacion(0.0, 0.0)
    assert está_degradado is False
    assert pct == 0.0


def test_obtener_error_promedio_desde_bd(db_session: Session):
    """Calcula promedio de error_s desde BD en rango."""
    from src.infrastructure.sqlalchemy.repositories.telemetria_repository import MySQLTelemetriaRepository

    repo = MySQLTelemetriaRepository(db_session)
    ahora = datetime.now(timezone.utc)

    db_session.execute(
        text(
            "INSERT INTO devices (id, device_uid, nombre, creado_en, actualizado_en) "
            "VALUES ('dev-probe-1', 'CC:DD:EE:FF:00:11', 'Probe1', :now, :now)"
        ),
        {"now": ahora},
    )
    db_session.commit()

    repo.guardar_anomalia("dev-probe-1", 10.0, ahora)
    repo.guardar_anomalia("dev-probe-1", 20.0, ahora - timedelta(hours=12))
    repo.guardar_anomalia("dev-probe-1", 15.0, ahora - timedelta(hours=36))
    repo.guardar_anomalia("dev-probe-1", 25.0, ahora - timedelta(days=8))

    promedio_24h = repo.obtener_error_promedio("dev-probe-1", ahora - timedelta(hours=24), ahora)
    assert promedio_24h == pytest.approx(15.0, abs=0.1)  # (10 + 20) / 2

    promedio_36h = repo.obtener_error_promedio("dev-probe-1", ahora - timedelta(hours=36), ahora)
    assert promedio_36h == pytest.approx(15.0, abs=0.1)  # (10 + 20 + 15) / 3

    promedio_sin_datos = repo.obtener_error_promedio(
        "dev-probe-1", ahora - timedelta(days=9), ahora - timedelta(days=8, hours=1)
    )
    assert promedio_sin_datos is None


def test_flujo_gauntlet_coherencia_diaria(db_session: Session):
    """Simula flujo diario: hoy se degrada vs baseline 7d → FAIL."""
    from src.infrastructure.sqlalchemy.repositories.telemetria_repository import MySQLTelemetriaRepository

    repo = MySQLTelemetriaRepository(db_session)
    ahora = datetime.now(timezone.utc)
    hace_7d = ahora - timedelta(days=7)
    hace_2d = ahora - timedelta(days=2)

    db_session.execute(
        text(
            "INSERT INTO devices (id, device_uid, nombre, creado_en, actualizado_en) "
            "VALUES ('dev-003', 'BB:CC:DD:EE:FF:00', 'Test3', :now, :now)"
        ),
        {"now": ahora},
    )
    db_session.commit()

    repo.guardar_anomalia("dev-003", 10.0, hace_7d)
    repo.guardar_anomalia("dev-003", 8.0, hace_7d + timedelta(days=2))
    repo.guardar_anomalia("dev-003", 20.0, hace_2d + timedelta(hours=6))
    repo.guardar_anomalia("dev-003", 22.0, ahora - timedelta(hours=1))

    baseline_7d = repo.obtener_error_promedio("dev-003", hace_7d, hace_2d)
    hoy_24h = repo.obtener_error_promedio("dev-003", hace_2d, ahora)

    assert baseline_7d == pytest.approx(9.0, abs=0.1)  # (10 + 8) / 2
    assert hoy_24h == pytest.approx(21.0, abs=0.1)  # (20 + 22) / 2

    está_degradado, pct_cambio = CalculadorCoherenciaService.evaluar_degradacion(hoy_24h, baseline_7d)
    assert está_degradado is True
    assert pct_cambio > 20.0

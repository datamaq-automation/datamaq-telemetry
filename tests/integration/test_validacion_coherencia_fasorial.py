"""tests/integration/test_validacion_coherencia_fasorial.py — Capa 1: Persistencia en BD."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.infrastructure.sqlalchemy.models import TelemetriaAnomaliaModel


class MockPotencia:
    """Mock de valor de potencia."""

    def __init__(self, valor: float, atributo: str):
        self.valor = valor
        self.vatios = valor if atributo == "vatios" else None
        self.var = valor if atributo == "var" else None
        self.va = valor if atributo == "va" else None


class MockLectura:
    """Mock de LecturaInstantanea."""

    def __init__(self, s_r=1300.0, s_s=1300.0, s_t=1300.0):
        self.potencia_activa_r = MockPotencia(1000.0, "vatios")
        self.potencia_reactiva_r = MockPotencia(500.0, "var")
        self.potencia_aparente_r = MockPotencia(s_r, "va")
        self.potencia_activa_s = MockPotencia(1000.0, "vatios")
        self.potencia_reactiva_s = MockPotencia(500.0, "var")
        self.potencia_aparente_s = MockPotencia(s_s, "va")
        self.potencia_activa_t = MockPotencia(1000.0, "vatios")
        self.potencia_reactiva_t = MockPotencia(500.0, "var")
        self.potencia_aparente_t = MockPotencia(s_t, "va")


@pytest.fixture
def lectura_coherencia_baja():
    """Lectura con error de coherencia > 15%."""
    return MockLectura()


@pytest.fixture
def lectura_coherencia_normal():
    """Lectura con error de coherencia < 15%."""
    return MockLectura(s_r=1150.0, s_s=1150.0, s_t=1150.0)


def test_guardar_anomalia_persistencia(db_session: Session):
    """Verifica que guardar_anomalia persiste en BD."""
    from src.infrastructure.sqlalchemy.repositories.telemetria_repository import MySQLTelemetriaRepository

    repo = MySQLTelemetriaRepository(db_session)
    ahora = datetime.now(timezone.utc)

    repo.guardar_anomalia("dev-001", 16.25, ahora)

    anomalia = db_session.query(TelemetriaAnomaliaModel).filter_by(device_id="dev-001").first()
    assert anomalia is not None
    assert anomalia.error_s == 16.25
    assert anomalia.flag_tipo == "coherencia_baja"
    assert anomalia.estado == "active"
    assert anomalia.contador_consecutivos == 1


def test_validacion_coherencia_detecta_baja(db_session: Session, lectura_coherencia_baja):
    """Verifica que _validar_coherencia_instantanea detecta y persiste anomalías."""
    from src.infrastructure.sqlalchemy.repositories.telemetria_repository import MySQLTelemetriaRepository

    repo = MySQLTelemetriaRepository(db_session)
    mock_logger = MagicMock()

    use_case = IngestarTelemetriaUseCase(
        repo_dispositivos=MagicMock(),
        repo_telemetria=repo,
        logger=mock_logger,
    )

    ahora = datetime.now(timezone.utc)
    use_case._validar_coherencia_instantanea(lectura_coherencia_baja, "dev-001", ahora)

    anomalia = db_session.query(TelemetriaAnomaliaModel).filter_by(device_id="dev-001").first()
    assert anomalia is not None
    assert anomalia.error_s > 15.0
    mock_logger.warning.assert_called()


def test_validacion_coherencia_no_detecta_normal(db_session: Session, lectura_coherencia_normal):
    """Verifica que no se persisten anomalías cuando error < 15%."""
    from src.infrastructure.sqlalchemy.repositories.telemetria_repository import MySQLTelemetriaRepository

    repo = MySQLTelemetriaRepository(db_session)
    mock_logger = MagicMock()

    use_case = IngestarTelemetriaUseCase(
        repo_dispositivos=MagicMock(),
        repo_telemetria=repo,
        logger=mock_logger,
    )

    ahora = datetime.now(timezone.utc)
    use_case._validar_coherencia_instantanea(lectura_coherencia_normal, "dev-001", ahora)

    anomalia = db_session.query(TelemetriaAnomaliaModel).filter_by(device_id="dev-001").first()
    assert anomalia is None
    mock_logger.warning.assert_not_called()


def test_anomalias_indexadas(db_session: Session):
    """Verifica que las anomalías se pueden recuperar eficientemente."""
    from sqlalchemy import text

    from src.infrastructure.sqlalchemy.repositories.telemetria_repository import MySQLTelemetriaRepository

    repo = MySQLTelemetriaRepository(db_session)
    ahora = datetime.now(timezone.utc)
    hace_1h = ahora - timedelta(hours=1)

    db_session.execute(
        text(
            "INSERT INTO devices (id, device_uid, nombre, creado_en, actualizado_en) "
            "VALUES ('dev-002', 'BB:CC:DD:EE:FF:00', 'Test2', :now, :now)"
        ),
        {"now": ahora},
    )
    db_session.commit()

    repo.guardar_anomalia("dev-001", 20.0, ahora)
    repo.guardar_anomalia("dev-001", 18.5, hace_1h)
    repo.guardar_anomalia("dev-002", 25.0, ahora)

    anomalias_dev1 = db_session.query(TelemetriaAnomaliaModel).filter_by(device_id="dev-001").all()
    assert len(anomalias_dev1) == 2

    anomalias_dev2 = db_session.query(TelemetriaAnomaliaModel).filter_by(device_id="dev-002").all()
    assert len(anomalias_dev2) == 1

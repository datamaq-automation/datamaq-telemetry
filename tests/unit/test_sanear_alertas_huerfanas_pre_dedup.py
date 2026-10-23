"""tests/unit/test_sanear_alertas_huerfanas_pre_dedup.py

Pruebas unitarias para el script de saneamiento retroactivo de alertas huérfanas pre-dedup (Issue #64).
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.sanear_alertas_huerfanas_pre_dedup import sanear_alertas_huerfanas
from src.infrastructure.sqlalchemy.models import Base, DeviceAlertModel, DeviceModel

T0 = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
AHORA = datetime(2026, 10, 23, 11, 0, tzinfo=timezone.utc)


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sesion = sessionmaker(bind=engine)()
    sesion.add_all(
        [
            DeviceModel(id="durax-01", device_uid="F8B3B7C0BBB0", name="Durax Vajillas", esta_activo=True),
            DeviceModel(id="sanmartin-01", device_uid="D48C49F035A8", name="San Martin Medición", esta_activo=True),
        ]
    )
    sesion.commit()
    yield sesion
    sesion.close()


def _crear_alerta(
    db: Session,
    device: str = "durax-01",
    tipo: str = "SOBRECOMPENSACION_REACTIVA",
    horas: int = 0,
    fase: str | None = None,
    is_resolved: bool = False,
    notes: str | None = None,
    occurrences: int = 1,
) -> DeviceAlertModel:
    a = DeviceAlertModel(
        id=(db.query(DeviceAlertModel).count() + 1),
        device_id=device,
        alert_type=tipo,
        severity="WARNING",
        message=f"Alerta a las {horas}h",
        triggered_at=T0 + timedelta(hours=horas),
        phase=fase,
        is_resolved=is_resolved,
        notes=notes,
        occurrences=occurrences,
        measured_value=Decimal("-10.5"),
    )
    db.add(a)
    db.commit()
    return a


def test_dry_run_no_modifica_db(db: Session):
    for h in range(3):
        _crear_alerta(db, horas=h)

    grupos = sanear_alertas_huerfanas(db, aplicar=False, ahora=AHORA)

    assert len(grupos) == 1
    assert grupos[0].conservada_id == 1
    assert len(grupos[0].resueltas_ids) == 2

    # En la base, al haber hecho rollback, siguen las 3 abiertas
    abiertas = db.query(DeviceAlertModel).filter(DeviceAlertModel.is_resolved.is_(False)).all()
    assert len(abiertas) == 3


def test_aplicar_conserva_mas_antigua_y_marca_duplicadas_como_resueltas(db: Session):
    for h in range(4):
        _crear_alerta(db, horas=h, occurrences=2)

    grupos = sanear_alertas_huerfanas(db, aplicar=True, ahora=AHORA)

    assert len(grupos) == 1
    grupo = grupos[0]
    assert grupo.conservada_id == 1
    assert set(grupo.resueltas_ids) == {2, 3, 4}
    assert grupo.ocurrencias_totales == 8

    # Verificar estado en DB
    abiertas = db.query(DeviceAlertModel).filter(DeviceAlertModel.is_resolved.is_(False)).all()
    assert len(abiertas) == 1
    conservada = abiertas[0]
    assert conservada.id == 1
    assert conservada.occurrences == 8
    assert conservada.last_detected_at == T0 + timedelta(hours=3)

    resueltas = db.query(DeviceAlertModel).filter(DeviceAlertModel.is_resolved.is_(True)).all()
    assert len(resueltas) == 3
    for r in resueltas:
        assert r.resolved_at == AHORA
        assert r.notes == "Saneamiento retroactivo pre-Issue #19"


def test_es_idempotente(db: Session):
    for h in range(3):
        _crear_alerta(db, horas=h)

    # Primera corrida
    grupos_1 = sanear_alertas_huerfanas(db, aplicar=True, ahora=AHORA)
    assert len(grupos_1) == 1

    # Segunda corrida no debe encontrar nada para sanear
    grupos_2 = sanear_alertas_huerfanas(db, aplicar=True, ahora=AHORA)
    assert len(grupos_2) == 0

    abiertas = db.query(DeviceAlertModel).filter(DeviceAlertModel.is_resolved.is_(False)).all()
    assert len(abiertas) == 1


def test_filtro_dispositivo_y_tipo(db: Session):
    # 2 alertas para Durax SOBRECOMPENSACION
    _crear_alerta(db, device="durax-01", tipo="SOBRECOMPENSACION_REACTIVA", horas=0)
    _crear_alerta(db, device="durax-01", tipo="SOBRECOMPENSACION_REACTIVA", horas=1)

    # 2 alertas para San Martin BAJO_FACTOR_POTENCIA
    _crear_alerta(db, device="sanmartin-01", tipo="BAJO_FACTOR_POTENCIA", horas=0)
    _crear_alerta(db, device="sanmartin-01", tipo="BAJO_FACTOR_POTENCIA", horas=1)

    # Filtrar solo por durax-01
    grupos_durax = sanear_alertas_huerfanas(db, aplicar=True, ahora=AHORA, dispositivo_id="durax-01")
    assert len(grupos_durax) == 1
    assert grupos_durax[0].device_id == "durax-01"

    # San Martin no debe haber sido tocado
    abiertas_sm = (
        db.query(DeviceAlertModel)
        .filter(DeviceAlertModel.device_id == "sanmartin-01", DeviceAlertModel.is_resolved.is_(False))
        .all()
    )
    assert len(abiertas_sm) == 2


def test_alertas_ya_resueltas_no_se_tocan(db: Session):
    _crear_alerta(db, horas=0, is_resolved=True, notes="Previamente resuelta")
    _crear_alerta(db, horas=1, is_resolved=False)

    grupos = sanear_alertas_huerfanas(db, aplicar=True, ahora=AHORA)
    assert len(grupos) == 0

    resueltas = db.query(DeviceAlertModel).filter(DeviceAlertModel.is_resolved.is_(True)).all()
    assert len(resueltas) == 1
    assert resueltas[0].notes == "Previamente resuelta"


def test_fases_distintas_no_se_mezclan(db: Session):
    _crear_alerta(db, horas=0, fase="R")
    _crear_alerta(db, horas=1, fase="R")
    _crear_alerta(db, horas=0, fase="S")

    grupos = sanear_alertas_huerfanas(db, aplicar=True, ahora=AHORA)
    assert len(grupos) == 1
    assert grupos[0].phase == "R"
    assert len(grupos[0].resueltas_ids) == 1

    abiertas = db.query(DeviceAlertModel).filter(DeviceAlertModel.is_resolved.is_(False)).all()
    assert len(abiertas) == 2


def test_main_cli(monkeypatch, capsys):
    from unittest.mock import MagicMock, patch

    from scripts.sanear_alertas_huerfanas_pre_dedup import main

    mock_db = MagicMock()
    with patch("src.infrastructure.sqlalchemy.database.get_session_factory") as mock_factory:
        mock_factory.return_value = MagicMock(return_value=mock_db)
        with patch("scripts.sanear_alertas_huerfanas_pre_dedup.sanear_alertas_huerfanas") as mock_sanear:
            mock_sanear.return_value = []
            monkeypatch.setattr("sys.argv", ["sanear_alertas_huerfanas_pre_dedup.py", "--dry-run"])
            main()
            mock_sanear.assert_called_once()
            assert mock_sanear.call_args.kwargs["aplicar"] is False
            captured = capsys.readouterr()
            assert "DRY-RUN" in captured.out

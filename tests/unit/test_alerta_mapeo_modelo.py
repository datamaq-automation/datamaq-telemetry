"""tests/unit/test_alerta_mapeo_modelo.py — La última detección y las ocurrencias sobreviven al guardado (#19)."""

from datetime import datetime, timedelta, timezone

from src.domain.telemetria.entities import AlertaDispositivo
from src.domain.telemetria.value_objects import SeveridadAlerta
from src.infrastructure.sqlalchemy.models import DeviceAlertModel
from src.infrastructure.sqlalchemy.repositories.telemetria_mappers import alerta_a_modelo, alerta_to_entity

T0 = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)


def _alerta() -> AlertaDispositivo:
    return AlertaDispositivo(
        id=7,
        dispositivo_id="bf2c",
        tipo_alerta="SOBRECOMPENSACION_REACTIVA",
        severidad=SeveridadAlerta.WARNING,
        mensaje="Q=-25 kvar",
        disparada_en=T0,
        fase=None,
        valor_medido=-25.0,
        ultima_deteccion_en=T0 + timedelta(hours=5),
        ocurrencias=116,
    )


def test_ida_y_vuelta_conserva_ultima_deteccion_y_ocurrencias():
    model = alerta_a_modelo(_alerta(), DeviceAlertModel())
    model.id = 7
    vuelta = alerta_to_entity(model)
    assert vuelta.ultima_deteccion_en == T0 + timedelta(hours=5)
    assert vuelta.ocurrencias == 116
    assert vuelta.valor_medido == -25.0
    assert vuelta.disparada_en == T0


def test_alerta_nueva_se_guarda_con_una_ocurrencia():
    alerta = _alerta()
    alerta.ocurrencias = 1
    alerta.ultima_deteccion_en = None
    model = alerta_a_modelo(alerta, DeviceAlertModel())
    assert model.occurrences == 1
    assert model.last_detected_at is None


def test_fila_vieja_sin_ocurrencias_se_lee_como_una():
    model = alerta_a_modelo(_alerta(), DeviceAlertModel())
    model.occurrences = None  # filas previas a la migración, antes del server_default
    assert alerta_to_entity(model).ocurrencias == 1

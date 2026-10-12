"""tests/unit/test_alerta_reincidencia.py — Una alerta abierta absorbe las nuevas detecciones de la misma condición (#19)."""

from datetime import datetime, timedelta, timezone

from src.domain.telemetria.entities import AlertaDispositivo
from src.domain.telemetria.value_objects import SeveridadAlerta

T0 = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)


def _alerta(tipo: str = "SOBRECOMPENSACION_REACTIVA", fase: str | None = None, **kw) -> AlertaDispositivo:
    base = {
        "id": None,
        "dispositivo_id": "bf2c",
        "tipo_alerta": tipo,
        "severidad": SeveridadAlerta.WARNING,
        "mensaje": "Q=-10 kvar",
        "disparada_en": T0,
        "fase": fase,
        "valor_medido": -10.0,
    }
    base.update(kw)
    return AlertaDispositivo(**base)


def test_equivalencia_por_dispositivo_tipo_y_fase():
    assert _alerta().es_equivalente(_alerta())
    assert not _alerta().es_equivalente(_alerta(tipo="BAJO_FACTOR_POTENCIA"))
    assert not _alerta(tipo="BAJA_TENSION", fase="R").es_equivalente(_alerta(tipo="BAJA_TENSION", fase="S"))
    assert not _alerta().es_equivalente(_alerta(dispositivo_id="otro"))


def test_reincidencia_conserva_el_inicio_y_actualiza_valores():
    abierta = _alerta()
    nueva = _alerta(disparada_en=T0 + timedelta(hours=3), mensaje="Q=-25 kvar", valor_medido=-25.0)

    abierta.registrar_reincidencia(nueva)
    abierta.registrar_reincidencia(_alerta(disparada_en=T0 + timedelta(hours=5), valor_medido=-30.0))

    assert abierta.disparada_en == T0
    assert abierta.ultima_deteccion_en == T0 + timedelta(hours=5)
    assert abierta.ocurrencias == 3
    assert abierta.valor_medido == -30.0
    assert not abierta.esta_resuelta


def test_alerta_nueva_arranca_con_una_ocurrencia():
    assert _alerta().ocurrencias == 1
    assert _alerta().ultima_deteccion_en is None

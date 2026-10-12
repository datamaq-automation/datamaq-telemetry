"""tests/unit/test_alcance_tiempo_real.py — A qué medidores renovar el modo de tiempo real (#15)."""

from datetime import datetime, timedelta, timezone

from src.domain.telemetria.servicios.alcance_tiempo_real import (
    VENTANA_RECEPCION_RECIENTE_S,
    AlcanceTiempoReal,
    alcance_de_clientes,
    publico_recientemente,
)

AHORA = datetime(2026, 10, 11, 21, 0, tzinfo=timezone.utc)


# --- Dominio: alcance ---


def test_alcance_sin_clientes_es_vacio():
    assert alcance_de_clientes([]).vacio


def test_alcance_junta_las_organizaciones_de_los_clientes():
    alcance = alcance_de_clientes([(False, "org-a"), (False, "org-b"), (False, "org-a")])
    assert alcance == AlcanceTiempoReal(todas=False, organizaciones=frozenset({"org-a", "org-b"}))


def test_un_superadmin_conectado_abarca_todas():
    assert alcance_de_clientes([(False, "org-a"), (True, None)]).todas


def test_cliente_sin_organizacion_ni_superadmin_no_aporta_alcance():
    assert alcance_de_clientes([(False, None)]).vacio


def test_cubre():
    todas = AlcanceTiempoReal(todas=True, organizaciones=frozenset())
    solo_a = AlcanceTiempoReal(todas=False, organizaciones=frozenset({"org-a"}))
    a_y_b = AlcanceTiempoReal(todas=False, organizaciones=frozenset({"org-a", "org-b"}))
    vacio = AlcanceTiempoReal(todas=False, organizaciones=frozenset())
    assert todas.cubre(a_y_b)
    assert a_y_b.cubre(solo_a)
    assert not solo_a.cubre(a_y_b)
    assert not a_y_b.cubre(todas)
    assert not vacio.cubre(solo_a)
    assert vacio.cubre(vacio)


# --- Dominio: recepción reciente ---


def test_publico_recientemente_respeta_la_ventana_de_10_minutos():
    assert VENTANA_RECEPCION_RECIENTE_S == 600
    assert publico_recientemente(AHORA - timedelta(seconds=600), AHORA)
    assert not publico_recientemente(AHORA - timedelta(seconds=601), AHORA)


def test_dispositivo_que_nunca_publico_no_es_reciente():
    assert not publico_recientemente(None, AHORA)

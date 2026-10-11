"""tests/unit/test_potencia_adquirida_mes_anterior.py — ventana del mes de facturación anterior."""

from datetime import datetime
from zoneinfo import ZoneInfo

from src.application.use_cases.consultar_nodo_unifilar import ventana_mes_anterior

TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def test_ventana_del_mes_anterior_en_mitad_de_mes():
    desde, hasta = ventana_mes_anterior(datetime(2026, 10, 11, 15, 36, tzinfo=TZ))

    assert desde == datetime(2026, 9, 1, 0, 0, tzinfo=TZ)
    assert hasta == datetime(2026, 10, 1, 0, 0, tzinfo=TZ)


def test_ventana_cruza_el_anio_desde_enero():
    desde, hasta = ventana_mes_anterior(datetime(2026, 1, 15, 8, 0, tzinfo=TZ))

    assert desde == datetime(2025, 12, 1, 0, 0, tzinfo=TZ)
    assert hasta == datetime(2026, 1, 1, 0, 0, tzinfo=TZ)


def test_justo_al_inicio_de_mes_la_ventana_es_el_mes_recien_cerrado():
    desde, hasta = ventana_mes_anterior(datetime(2026, 3, 1, 0, 0, tzinfo=TZ))

    assert desde == datetime(2026, 2, 1, 0, 0, tzinfo=TZ)
    assert hasta == datetime(2026, 3, 1, 0, 0, tzinfo=TZ)


def test_mes_anterior_de_febrero_no_bisiesto_tiene_28_dias():
    desde, hasta = ventana_mes_anterior(datetime(2027, 3, 5, 12, 0, tzinfo=TZ))

    assert (hasta - desde).days == 28

"""tests/unit/test_calculador_demanda_cuartohoraria.py

Pruebas unitarias para el cálculo de demanda cuarto-horaria (bloques de 15 minutos)
segregada en Horas Punta (18:00 a 23:00) y Fuera de Punta en horario argentino.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from src.domain.telemetria.servicios.agregador_dispositivos import PuntoPotencia
from src.domain.telemetria.servicios.calculador_demanda_cuartohoraria import (
    CalculadorDemandaCuartohorariaService,
    DemandaCuartohoraria,
)

ZONA_BSAS = ZoneInfo("America/Argentina/Buenos_Aires")


def test_es_hora_punta_segregacion():
    # 18:00 hora local en Argentina es hora punta
    dt_1800_local = datetime(2026, 10, 1, 18, 0, 0, tzinfo=ZONA_BSAS)
    assert CalculadorDemandaCuartohorariaService.es_hora_punta(dt_1800_local) is True

    # 22:45 hora local es hora punta
    dt_2245_local = datetime(2026, 10, 1, 22, 45, 0, tzinfo=ZONA_BSAS)
    assert CalculadorDemandaCuartohorariaService.es_hora_punta(dt_2245_local) is True

    # 17:45 hora local es fuera de punta
    dt_1745_local = datetime(2026, 10, 1, 17, 45, 0, tzinfo=ZONA_BSAS)
    assert CalculadorDemandaCuartohorariaService.es_hora_punta(dt_1745_local) is False

    # 23:00 hora local es fuera de punta (punta es [18, 23))
    dt_2300_local = datetime(2026, 10, 1, 23, 0, 0, tzinfo=ZONA_BSAS)
    assert CalculadorDemandaCuartohorariaService.es_hora_punta(dt_2300_local) is False

    # 12:00 mediodía es fuera de punta
    dt_1200_local = datetime(2026, 10, 1, 12, 0, 0, tzinfo=ZONA_BSAS)
    assert CalculadorDemandaCuartohorariaService.es_hora_punta(dt_1200_local) is False


def test_es_hora_punta_con_timestamp_utc():
    # 18:00 ART (UTC-3) corresponde a 21:00 UTC
    dt_utc = datetime(2026, 10, 1, 21, 0, 0, tzinfo=timezone.utc)
    assert CalculadorDemandaCuartohorariaService.es_hora_punta(dt_utc) is True

    # 17:59 ART corresponde a 20:59 UTC
    dt_utc_fp = datetime(2026, 10, 1, 20, 59, 0, tzinfo=timezone.utc)
    assert CalculadorDemandaCuartohorariaService.es_hora_punta(dt_utc_fp) is False


def test_calcular_demanda_sin_bloques():
    resultado = CalculadorDemandaCuartohorariaService.calcular_demanda([])
    assert resultado == DemandaCuartohoraria(
        potencia_adquirida_punta_kw=None,
        potencia_adquirida_fuera_punta_kw=None,
        momento_pico_punta=None,
        momento_pico_fuera_punta=None,
        bloques_evaluados=0,
    )


def test_calcular_demanda_bloques_punta_y_fuera_punta():
    # 18:00 ART (21:00 UTC): 500.0 kW (500_000 W)
    t1 = datetime(2026, 10, 1, 21, 0, 0, tzinfo=timezone.utc)
    # 18:15 ART (21:15 UTC): 750.0 kW (750_000 W) -> PICO PUNTA
    t2 = datetime(2026, 10, 1, 21, 15, 0, tzinfo=timezone.utc)
    # 10:00 ART (13:00 UTC): 300.0 kW (300_000 W)
    t3 = datetime(2026, 10, 1, 13, 0, 0, tzinfo=timezone.utc)
    # 14:30 ART (17:30 UTC): 420.0 kW (420_000 W) -> PICO FUERA DE PUNTA
    t4 = datetime(2026, 10, 1, 17, 30, 0, tzinfo=timezone.utc)

    puntos = [
        PuntoPotencia(momento=t1, potencia_activa_total_w=500_000.0, dispositivos_sin_dato=[]),
        PuntoPotencia(momento=t2, potencia_activa_total_w=750_000.0, dispositivos_sin_dato=[]),
        PuntoPotencia(momento=t3, potencia_activa_total_w=300_000.0, dispositivos_sin_dato=[]),
        PuntoPotencia(momento=t4, potencia_activa_total_w=420_000.0, dispositivos_sin_dato=[]),
    ]

    resultado = CalculadorDemandaCuartohorariaService.calcular_demanda(puntos)
    assert resultado.potencia_adquirida_punta_kw == pytest.approx(750.0)
    assert resultado.momento_pico_punta == t2
    assert resultado.potencia_adquirida_fuera_punta_kw == pytest.approx(420.0)
    assert resultado.momento_pico_fuera_punta == t4
    assert resultado.bloques_evaluados == 4


def test_calcular_demanda_desde_lecturas_agrega_a_15min_y_suma_dispositivos():
    # Dos dispositivos en acometida con lecturas en el mismo bloque de 15 minutos:
    # Bloque 18:00 a 18:15 ART (21:00 UTC)
    t_1802 = datetime(2026, 10, 1, 21, 2, 0, tzinfo=timezone.utc)
    t_1810 = datetime(2026, 10, 1, 21, 10, 0, tzinfo=timezone.utc)

    # Dispositivo 1 reporta 100 kW y luego 120 kW en ese bloque (promedio = 110 kW = 110_000 W)
    # Dispositivo 2 reporta 200 kW en ese bloque (promedio = 200 kW = 200_000 W)
    # Total sumado del bloque = 310 kW
    lecturas = {
        "dev-1": [(t_1802, 100_000.0, None), (t_1810, 120_000.0, None)],
        "dev-2": [(t_1802, 200_000.0, None)],
    }

    resultado = CalculadorDemandaCuartohorariaService.calcular_demanda_desde_lecturas(lecturas)
    assert resultado.potencia_adquirida_punta_kw == pytest.approx(310.0)
    assert resultado.potencia_adquirida_fuera_punta_kw is None
    assert resultado.bloques_evaluados == 1

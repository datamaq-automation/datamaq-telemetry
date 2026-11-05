"""tests/unit/test_agregador_huecos_interpolacion.py — hueco de un medidor en un bucket (datamaq-automation/datamaq#94).

Si un medidor no tiene dato en un bucket pero sí lo tiene antes y después, a no más de 15 min,
su potencia se interpola linealmente en ese bucket. Huecos más largos, o en el borde de la
ventana, siguen como antes: suma parcial y el medidor en ``dispositivos_sin_dato``.
"""

from datetime import datetime, timedelta, timezone

from src.domain.telemetria.servicios.agregador_dispositivos import AgregadorDispositivosService
from src.domain.telemetria.servicios.calculador_demanda_cuartohoraria import CalculadorDemandaCuartohorariaService

BASE = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
INTERVALO_5_MIN = 300


def _t(minutos: int) -> datetime:
    return BASE + timedelta(minutes=minutos)


def _por_momento(resultado):
    return {p.momento: p for p in resultado}


def test_hueco_de_un_bucket_se_interpola_linealmente():
    lecturas = {
        "trafo-01": [(_t(0), 1000.0), (_t(10), 3000.0)],  # sin dato en 12:05
        "trafo-02": [(_t(0), 500.0), (_t(5), 500.0), (_t(10), 500.0)],
    }

    resultado = _por_momento(
        AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, intervalo_segundos=INTERVALO_5_MIN)
    )

    # Bucket 12:05: trafo-01 interpolado = 1000 + (3000 - 1000) * 5/10 = 2000; más trafo-02 = 500.
    assert resultado[_t(5)].potencia_activa_total_w == 2500.0
    assert resultado[_t(5)].dispositivos_interpolados == ["trafo-01"]
    # Los buckets con dato real no marcan interpolación.
    assert resultado[_t(0)].potencia_activa_total_w == 1500.0
    assert resultado[_t(0)].dispositivos_interpolados == []


def test_hueco_de_dos_buckets_se_interpola_si_cada_vecino_esta_a_15_min_o_menos():
    lecturas = {
        "trafo-01": [(_t(0), 1000.0), (_t(15), 4000.0)],  # sin dato en 12:05 ni en 12:10
        "trafo-02": [(_t(0), 500.0), (_t(5), 500.0), (_t(10), 500.0), (_t(15), 500.0)],
    }

    resultado = _por_momento(
        AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, intervalo_segundos=INTERVALO_5_MIN)
    )

    # 12:05 → 1000 + 3000 * 1/3 = 2000 ; 12:10 → 1000 + 3000 * 2/3 = 3000
    assert resultado[_t(5)].potencia_activa_total_w == 2500.0
    assert resultado[_t(10)].potencia_activa_total_w == 3500.0
    assert resultado[_t(5)].dispositivos_interpolados == ["trafo-01"]
    assert resultado[_t(10)].dispositivos_interpolados == ["trafo-01"]


def test_hueco_mayor_a_15_min_no_se_interpola_y_queda_como_suma_parcial():
    # trafo-01 tiene 1000 W a 12:00 y 3000 W a 12:25. El bucket 12:05 queda a 20 min de la lectura
    # posterior: un vecino a más de 15 min no permite interpolar. El 12:10 sí (10 y 15 min).
    lecturas = {
        "trafo-01": [(_t(0), 1000.0), (_t(25), 3000.0)],
        "trafo-02": [(_t(m), 500.0) for m in (0, 5, 10, 15, 20, 25)],
    }

    resultado = _por_momento(
        AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, intervalo_segundos=INTERVALO_5_MIN)
    )

    assert resultado[_t(5)].potencia_activa_total_w == 500.0
    assert resultado[_t(5)].dispositivos_sin_dato == ["trafo-01"]
    assert resultado[_t(5)].dispositivos_interpolados == []
    assert resultado[_t(10)].dispositivos_interpolados == ["trafo-01"]


def test_hueco_en_el_borde_de_la_ventana_no_se_interpola():
    # trafo-01 no tiene lectura antes de 12:05: el bucket 12:00 no tiene vecino anterior.
    lecturas = {
        "trafo-01": [(_t(5), 1000.0), (_t(10), 1000.0)],
        "trafo-02": [(_t(0), 500.0), (_t(5), 500.0), (_t(10), 500.0)],
    }

    resultado = _por_momento(
        AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, intervalo_segundos=INTERVALO_5_MIN)
    )

    assert resultado[_t(0)].potencia_activa_total_w == 500.0
    assert resultado[_t(0)].dispositivos_sin_dato == ["trafo-01"]
    assert resultado[_t(0)].dispositivos_interpolados == []


def test_vecino_sin_reactiva_interpola_p_pero_deja_q_en_none():
    lecturas = {
        "trafo-01": [(_t(0), 1000.0, 500.0), (_t(10), 3000.0, None)],  # el vecino posterior no tiene Q
        "trafo-02": [(_t(0), 500.0, 0.0), (_t(5), 500.0, 0.0), (_t(10), 500.0, 0.0)],
    }

    resultado = _por_momento(
        AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, intervalo_segundos=INTERVALO_5_MIN)
    )

    assert resultado[_t(5)].potencia_activa_total_w == 2500.0
    assert resultado[_t(5)].potencia_reactiva_total_var is None
    assert resultado[_t(5)].dispositivos_interpolados == ["trafo-01"]


def test_demanda_cuartohoraria_con_medidor_faltante_usa_el_valor_interpolado():
    # Bloques de 15 min. trafo-01 no tiene dato a 12:15 (hay 2000 W a 12:00 y a 12:30).
    # trafo-02 tiene 3000 W a 12:15. El pico de demanda debe ser 5 kW en 12:15, no 3 kW.
    lecturas = {
        "trafo-01": [(_t(0), 2000.0), (_t(30), 2000.0)],
        "trafo-02": [(_t(0), 0.0), (_t(15), 3000.0), (_t(30), 0.0)],
    }

    demanda = CalculadorDemandaCuartohorariaService.calcular_demanda_desde_lecturas(lecturas, zona="UTC")

    assert demanda.potencia_adquirida_fuera_punta_kw == 5.0
    assert demanda.momento_pico_fuera_punta == _t(15)

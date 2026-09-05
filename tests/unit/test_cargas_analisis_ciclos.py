"""Extracción y caracterización de ciclos de encendido sobre la serie de potencia."""

from datetime import datetime, timedelta, timezone

from src.domain.cargas.servicios.analizador_ciclos import AnalizadorCiclosService
from src.domain.cargas.value_objects import PatronOperacion
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal

INICIO = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
CADENCIA_5_MIN = 300.0


def _serie(potencias: list[float], cadencia_s: float = CADENCIA_5_MIN) -> list[LecturaPotenciaTemporal]:
    return [
        LecturaPotenciaTemporal(momento=INICIO + timedelta(seconds=i * cadencia_s), potencia_w=p)
        for i, p in enumerate(potencias)
    ]


def _heladera(ciclos: int, muestras_on: int = 5, muestras_off: int = 9) -> list[float]:
    """Compresor regular: ~25 min encendido a 120 W, ~45 min apagado a 20 W de standby."""
    patron: list[float] = [20.0, 20.0]
    for _ in range(ciclos):
        patron += [120.0] * muestras_on + [20.0] * muestras_off
    return patron


def test_serie_corta_no_produce_estadistica():
    """Por debajo del mínimo de lecturas no se afirma nada."""
    resultado = AnalizadorCiclosService.analizar(_serie([120.0] * 10), umbral_encendido_w=60.0)

    assert resultado.ciclos == 0
    assert resultado.patron == PatronOperacion.INDETERMINADO
    assert resultado.duty_cycle is None


def test_un_pico_de_una_sola_muestra_no_cuenta_como_ciclo():
    """Indistinguible de una lectura espuria: no debe generar un encendido."""
    potencias = [20.0] * 15 + [2000.0] + [20.0] * 15
    ciclos = AnalizadorCiclosService.extraer_ciclos(_serie(potencias), umbral_encendido_w=60.0)

    assert ciclos == []


def test_ciclado_regular_de_heladera_se_reconoce_como_termostatico():
    resultado = AnalizadorCiclosService.analizar(_serie(_heladera(ciclos=8)), umbral_encendido_w=60.0)

    assert resultado.ciclos == 8
    assert resultado.patron == PatronOperacion.CICLICO_TERMOSTATICO
    assert resultado.es_regular is True


def test_las_duraciones_de_encendido_e_inactividad_se_miden_por_separado():
    """El par funcionamiento/inactividad es el resultado central del análisis."""
    resultado = AnalizadorCiclosService.analizar(_serie(_heladera(ciclos=8)), umbral_encendido_w=60.0)

    # 5 muestras encendido = 4 intervalos de 300 s + la cadencia que representa la última.
    assert resultado.duracion_encendido_mediana_s == 1500.0
    # 9 muestras apagado entre el fin de un encendido y el inicio del siguiente.
    assert resultado.duracion_apagado_mediana_s == 3000.0
    assert resultado.periodo_mediano_s == 4500.0


def test_el_duty_cycle_refleja_la_fraccion_de_tiempo_en_marcha():
    resultado = AnalizadorCiclosService.analizar(_serie(_heladera(ciclos=8)), umbral_encendido_w=60.0)

    assert resultado.duty_cycle is not None
    assert 0.30 < resultado.duty_cycle < 0.36


def test_un_ciclado_irregular_no_se_declara_termostatico():
    """Duraciones dispares: no hay termostato detrás, y el servicio no lo inventa."""
    potencias = [20.0, 20.0]
    for on, off in ((3, 4), (11, 2), (2, 15), (9, 3), (4, 9), (14, 2), (2, 11)):
        potencias += [120.0] * on + [20.0] * off

    resultado = AnalizadorCiclosService.analizar(_serie(potencias), umbral_encendido_w=60.0)

    assert resultado.patron != PatronOperacion.CICLICO_TERMOSTATICO
    assert resultado.es_regular is False


def test_una_carga_siempre_encendida_es_continua():
    resultado = AnalizadorCiclosService.analizar(_serie([150.0] * 40), umbral_encendido_w=60.0)

    assert resultado.duty_cycle == 1.0
    assert resultado.patron == PatronOperacion.CONTINUO_DIARIO


def test_un_hueco_de_datos_corta_el_ciclo_en_lugar_de_prolongarlo():
    """Sin este corte, una caída del medidor inventaría un encendido de horas."""
    antes = _serie([20.0] * 5 + [120.0] * 4)
    despues = [
        LecturaPotenciaTemporal(
            momento=antes[-1].momento + timedelta(hours=6) + timedelta(seconds=i * 300), potencia_w=p
        )
        for i, p in enumerate([120.0] * 4 + [20.0] * 10)
    ]

    ciclos = AnalizadorCiclosService.extraer_ciclos(antes + despues, umbral_encendido_w=60.0)

    assert len(ciclos) == 2
    assert all(c.duracion_encendido_s < 3600 for c in ciclos)


def test_la_histeresis_rescata_una_carga_que_oscila_en_la_frontera_del_umbral():
    """Sin histéresis, una carga que roza el umbral se fragmenta y desaparece.

    Cada tramo queda de una sola muestra, y una sola muestra se descarta por espuria:
    el resultado es que la carga no se detecta en absoluto. Con un umbral de apagado
    más bajo, el mismo encendido se lee como el único ciclo que realmente fue.
    """
    potencias = [20.0] * 4 + [125.0, 118.0, 124.0, 117.0, 126.0, 119.0, 123.0] + [20.0] * 10

    sin_histeresis = AnalizadorCiclosService.extraer_ciclos(_serie(potencias), umbral_encendido_w=120.0)
    con_histeresis = AnalizadorCiclosService.extraer_ciclos(
        _serie(potencias), umbral_encendido_w=120.0, umbral_apagado_w=60.0
    )

    assert sin_histeresis == []
    assert len(con_histeresis) == 1
    assert con_histeresis[0].muestras == 7


def test_a_cadencia_de_5_min_un_encendido_de_2_min_no_se_detecta():
    """Límite de instrumentación declarado: la pava no existe para este servicio.

    No es una carencia del algoritmo — el hardware nunca midió el evento — y por eso el
    resultado correcto es no reportar nada, no reportar algo con baja confianza.
    """
    potencias = [20.0] * 15 + [2200.0] + [20.0] * 15

    resultado = AnalizadorCiclosService.analizar(_serie(potencias), umbral_encendido_w=1000.0)

    assert resultado.ciclos == 0


def test_a_cadencia_de_5_s_el_mismo_encendido_de_2_min_si_se_detecta():
    """El mismo código, con la resolución que da una campaña de ráfaga, sí lo ve."""
    potencias = [20.0] * 20 + [2200.0] * 24 + [20.0] * 20

    resultado = AnalizadorCiclosService.analizar(_serie(potencias, cadencia_s=5.0), umbral_encendido_w=1000.0)

    assert resultado.ciclos == 1
    assert (
        AnalizadorCiclosService.extraer_ciclos(_serie(potencias, cadencia_s=5.0), umbral_encendido_w=1000.0)[
            0
        ].duracion_encendido_s
        == 120.0
    )

"""tests/unit/test_cargas_linea_base.py — Perfil de línea de base: separar el consumo permanente del consumo de actividad."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.domain.cargas.servicios.perfilador_linea_base import PerfiladorLineaBaseService
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal

BUENOS_AIRES = ZoneInfo("America/Argentina/Buenos_Aires")
INICIO = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)


def _casa(dias: int = 3, base_noche: float = 110.0, extra_dia: float = 250.0) -> list[LecturaPotenciaTemporal]:
    """Casa sintética: refrigeración de fondo siempre, más actividad en horario diurno.

    Cadencia de 5 minutos, que es la real de la plataforma en modo estándar.
    """
    lecturas: list[LecturaPotenciaTemporal] = []
    muestras = dias * 24 * 12
    for i in range(muestras):
        momento = INICIO + timedelta(seconds=i * 300)
        hora_local = momento.astimezone(BUENOS_AIRES).hour
        potencia = base_noche + (extra_dia if 10 <= hora_local <= 22 else 0.0)
        # Ciclado del compresor por encima de la base, en cualquier franja.
        if i % 14 < 5:
            potencia += 120.0
        lecturas.append(LecturaPotenciaTemporal(momento=momento, potencia_w=potencia))
    return lecturas


def test_serie_insuficiente_no_inventa_linea_base():
    lecturas = _casa()[:10]

    perfil = PerfiladorLineaBaseService.perfilar(lecturas, zona=BUENOS_AIRES)

    assert perfil.linea_base_nocturna_w is None
    assert perfil.delta_diurno_w is None
    assert perfil.muestras == 10


def test_la_linea_base_nocturna_captura_solo_las_cargas_autonomas():
    """De madrugada solo queda la refrigeración: la base debe dar el fondo, no el pico."""
    perfil = PerfiladorLineaBaseService.perfilar(_casa(), zona=BUENOS_AIRES)

    assert perfil.linea_base_nocturna_w == 110.0
    assert perfil.ventanas_nocturnas > 0


def test_el_delta_diurno_mide_lo_que_se_suma_de_dia_sin_bautizarlo():
    """No es "iluminación": es todo lo que no se puede separar en escalones a 5 min."""
    perfil = PerfiladorLineaBaseService.perfilar(_casa(extra_dia=250.0), zona=BUENOS_AIRES)

    assert perfil.linea_base_diurna_w == 360.0
    assert perfil.delta_diurno_w == 250.0


def test_el_percentil_bajo_ignora_un_outlier_que_arruinaria_al_minimo():
    """El mínimo lo fija una sola lectura; el percentil 10 sobre la ventana sobrevive."""
    lecturas = _casa()
    contaminadas = [
        LecturaPotenciaTemporal(momento=lectura.momento, potencia_w=0.5 if i == 40 else lectura.potencia_w)
        for i, lectura in enumerate(lecturas)
    ]

    limpio = PerfiladorLineaBaseService.perfilar(lecturas, zona=BUENOS_AIRES)
    contaminado = PerfiladorLineaBaseService.perfilar(contaminadas, zona=BUENOS_AIRES)

    assert contaminado.linea_base_nocturna_w == limpio.linea_base_nocturna_w


def test_el_perfil_declara_la_cadencia_que_encontro():
    """Todo umbral temporal depende de la cadencia real, así que se reporta."""
    perfil = PerfiladorLineaBaseService.perfilar(_casa(), zona=BUENOS_AIRES)

    assert perfil.cadencia_mediana_s == 300.0


def test_la_zona_horaria_decide_que_es_de_madrugada():
    """La zona no es cosmética: define qué ventana se toma como "sin actividad".

    Buenos Aires es UTC-3, así que la franja 02-04 UTC cae en las 23-01 locales. Con
    una casa activa a esa hora, evaluar la franja en UTC mide plena actividad y devuelve
    una línea de base falsa, más de tres veces la real.
    """
    lecturas = [
        LecturaPotenciaTemporal(
            momento=INICIO + timedelta(seconds=i * 300),
            potencia_w=110.0
            + (250.0 if (INICIO + timedelta(seconds=i * 300)).astimezone(BUENOS_AIRES).hour in (23, 0, 1) else 0.0),
        )
        for i in range(3 * 24 * 12)
    ]

    local = PerfiladorLineaBaseService.perfilar(lecturas, zona=BUENOS_AIRES)
    utc = PerfiladorLineaBaseService.perfilar(lecturas, zona=timezone.utc)

    assert local.linea_base_nocturna_w == 110.0
    assert utc.linea_base_nocturna_w == 360.0


def test_la_potencia_maxima_no_se_confunde_con_la_linea_base():
    perfil = PerfiladorLineaBaseService.perfilar(_casa(), zona=BUENOS_AIRES)

    assert perfil.potencia_maxima_w == 480.0
    assert perfil.linea_base_w is not None
    assert perfil.linea_base_w < perfil.potencia_maxima_w

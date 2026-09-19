# tests/unit/test_downsampler_lttb.py
from datetime import datetime, timedelta, timezone

from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
from src.domain.telemetria.services import AnalizadorCalidadEnergiaService
from src.domain.telemetria.servicios.agregador_lecturas import AgregadorLecturasService
from src.domain.telemetria.value_objects import PotenciaActiva


def _crear_lectura(dt: datetime, potencia_w: float) -> LecturaInstantanea:
    fase_vacia = MedicionFase()
    return LecturaInstantanea(
        id=None,
        dispositivo_id="dev-01",
        registrado_en=dt,
        fase_r=fase_vacia,
        fase_s=fase_vacia,
        fase_t=fase_vacia,
        potencia_activa_total=PotenciaActiva(vatios=potencia_w),
    )


def test_lttb_retorna_mismo_si_menor_o_igual_al_target():
    t0 = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
    lecturas = [_crear_lectura(t0 + timedelta(minutes=i), 1000.0) for i in range(5)]

    res = AgregadorLecturasService.downsample_lttb(lecturas, target_points=10)
    assert len(res) == 5
    assert res == lecturas


def test_lttb_preserva_primera_y_ultima_lectura():
    t0 = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
    lecturas = [_crear_lectura(t0 + timedelta(minutes=i), float(i * 100)) for i in range(20)]

    res = AgregadorLecturasService.downsample_lttb(lecturas, target_points=5)
    assert len(res) == 5
    assert res[0].registrado_en == lecturas[0].registrado_en
    assert res[-1].registrado_en == lecturas[-1].registrado_en


def test_lttb_preserva_picos_transitorios_de_potencia():
    t0 = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
    # 50 lecturas planas en 5000 W, con un pico de 150000 W en el índice 25
    lecturas = [_crear_lectura(t0 + timedelta(seconds=i * 10), 5000.0) for i in range(50)]
    lecturas[25] = _crear_lectura(t0 + timedelta(seconds=25 * 10), 150000.0)

    # Reducimos a solo 8 puntos
    res = AgregadorLecturasService.downsample_lttb(lecturas, target_points=8)
    assert len(res) == 8

    potencias = [
        item.potencia_activa_total.vatios
        for item in res
        if item.potencia_activa_total and item.potencia_activa_total.vatios is not None
    ]
    # El pico de 150000 W DEBE estar presente entre los puntos preservados
    assert 150000.0 in potencias


def test_lttb_mantiene_orden_descendente_si_entrada_es_descendente():
    t0 = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
    # Entrada en orden descendente (más reciente primero, como devuelve repo_telemetria.listar_instantaneas)
    lecturas = [_crear_lectura(t0 + timedelta(minutes=i), float(i * 100)) for i in range(20, 0, -1)]
    assert lecturas[0].registrado_en > lecturas[-1].registrado_en

    res = AgregadorLecturasService.downsample_lttb(lecturas, target_points=5)
    assert len(res) == 5
    # La salida debe conservar el orden descendente
    assert res[0].registrado_en > res[-1].registrado_en


def test_lttb_expuesto_en_analizador_calidad_energia():
    t0 = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
    lecturas = [_crear_lectura(t0 + timedelta(minutes=i), 2000.0) for i in range(15)]

    res = AnalizadorCalidadEnergiaService.downsample_lttb(lecturas, target_points=5)
    assert len(res) == 5

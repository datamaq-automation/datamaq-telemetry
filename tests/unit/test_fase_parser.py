import math

from src.application.mappers.fase_parser import aplicar_configuracion_ti
from src.domain.telemetria.entities import MedicionFase
from src.domain.telemetria.value_objects import PotenciaActiva, PotenciaReactiva


def _mf(p, q):
    return MedicionFase(
        potencia_activa=PotenciaActiva(vatios=float(p)),
        potencia_reactiva=PotenciaReactiva(var=float(q)),
    )


def test_identidad_no_cambia():
    r, s, t = _mf(1, 0), _mf(2, 0), _mf(3, 0)
    fr, fs, ft = aplicar_configuracion_ti(r, s, t, invertido=False, orden_fases=None)
    assert fr.potencia_activa.vatios == 1
    assert fs.potencia_activa.vatios == 2
    assert ft.potencia_activa.vatios == 3


def test_invertido_invierte_signo_pq():
    r, s, t = _mf(10, 5), _mf(20, 2), _mf(30, 3)
    fr, _fs, _ft = aplicar_configuracion_ti(r, s, t, invertido=True, orden_fases=None)
    assert fr.potencia_activa.vatios == -10
    assert fr.potencia_reactiva.var == -5


def test_reordenacion_permute_y_rota():
    # entradas: R=1, S=2, T=3; orden_fases = ['S','T','R'] -> expect transformed values
    r, s, t = _mf(1, 0), _mf(2, 0), _mf(3, 0)
    fr, fs, ft = aplicar_configuracion_ti(
        r, s, t, invertido=False, orden_fases=["S", "T", "R"]
    )

    # Expected (manual): fr comes from entrada T (3) rotated by -240deg (== +120deg)
    # cos(120) = -0.5 -> p' = 3 * -0.5 = -1.5
    assert math.isclose(fr.potencia_activa.vatios, -1.5, rel_tol=1e-6)

    # fs comes from entrada R (1) rotated by +120deg -> p' = 1 * -0.5 = -0.5
    assert math.isclose(fs.potencia_activa.vatios, -0.5, rel_tol=1e-6)

    # ft comes from entrada S (2) rotated by +120deg -> p' = 2 * -0.5 = -1.0
    assert math.isclose(ft.potencia_activa.vatios, -1.0, rel_tol=1e-6)


def test_reordenacion_mas_inversion_aplica_ambas():
    r, s, t = _mf(1, 0), _mf(2, 0), _mf(3, 0)
    fr, fs, ft = aplicar_configuracion_ti(
        r, s, t, invertido=True, orden_fases=["S", "T", "R"]
    )
    assert math.isclose(fr.potencia_activa.vatios, 1.5, rel_tol=1e-6)
    assert math.isclose(fs.potencia_activa.vatios, 0.5, rel_tol=1e-6)
    assert math.isclose(ft.potencia_activa.vatios, 1.0, rel_tol=1e-6)

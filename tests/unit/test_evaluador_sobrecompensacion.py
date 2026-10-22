"""tests/unit/test_evaluador_sobrecompensacion.py — Texto de la alerta de sobrecompensación reactiva (#20).

El texto de `observaciones` es el oficial aprobado por el dueño (decisions/2026-10-11_texto-sobrecompensacion-reactiva.md):
notifica, sin recomendar acciones.
"""

from datetime import datetime, timezone

from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
from src.domain.telemetria.servicios.evaluador_anomalias_fases import EvaluadorAnomaliasFasesService
from src.domain.telemetria.value_objects import PotenciaActiva, PotenciaReactiva

_DISPOSITIVO = "dev-consumo-01"
_TEXTO_OFICIAL = "Banco de capacitores sobredimensionado o con pasos encendidos en vacío."


def _lectura(p_w: float, q_var: float) -> LecturaInstantanea:
    vacia = MedicionFase()
    return LecturaInstantanea(
        id=None,
        dispositivo_id=_DISPOSITIVO,
        registrado_en=datetime(2026, 10, 2, 9, 0, 0, tzinfo=timezone.utc),
        fase_r=vacia,
        fase_s=vacia,
        fase_t=vacia,
        potencia_activa_total=PotenciaActiva(p_w),
        potencia_reactiva_total=PotenciaReactiva(q_var),
    )


def test_sobrecompensacion_usa_el_texto_oficial():
    alerta = EvaluadorAnomaliasFasesService.evaluar_alerta_sobrecompensacion_reactiva(
        _DISPOSITIVO, _lectura(p_w=1000.0, q_var=-800.0)
    )
    assert alerta is not None
    assert alerta.observaciones == _TEXTO_OFICIAL


def test_sin_sobrecompensacion_no_hay_alerta():
    alerta = EvaluadorAnomaliasFasesService.evaluar_alerta_sobrecompensacion_reactiva(
        _DISPOSITIVO, _lectura(p_w=1000.0, q_var=-100.0)
    )
    assert alerta is None

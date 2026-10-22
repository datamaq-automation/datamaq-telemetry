"""tests/unit/test_evaluador_potencia_negativa.py — Detector de potencia negativa (inyección indeseada).

Contra el diseño ACTUAL: el evaluador es puro (devuelve la alerta cruda) y la persistencia la decide
FiltroPersistenciaTemporalService (2 lecturas consecutivas o 3 s). La spec original proponía un contador
en telemetria_anomalias; ver specs/detector-potencia-negativa.md, sección "Desvío de diseño".
"""

from datetime import datetime, timedelta, timezone

from src.domain.telemetria.entities import (
    LecturaInstantanea,
    MedicionFase,
    SeveridadAlerta,
)
from src.domain.telemetria.servicios.evaluador_anomalias_fases import EvaluadorAnomaliasFasesService
from src.domain.telemetria.servicios.evaluador_potencia_negativa import EvaluadorPotenciaNegativaService
from src.domain.telemetria.servicios.persistencia_alertas import FiltroPersistenciaTemporalService
from src.domain.telemetria.value_objects import PotenciaActiva

_DISPOSITIVO = "dev-consumo-01"
_T0 = datetime(2026, 10, 2, 9, 0, 0, tzinfo=timezone.utc)


def _lectura(p_total_w: float | None, registrado_en: datetime = _T0) -> LecturaInstantanea:
    vacia = MedicionFase()
    return LecturaInstantanea(
        id=None,
        dispositivo_id=_DISPOSITIVO,
        registrado_en=registrado_en,
        fase_r=vacia,
        fase_s=vacia,
        fase_t=vacia,
        potencia_activa_total=None if p_total_w is None else PotenciaActiva(p_total_w),
    )


def test_potencia_negativa_bajo_umbral_genera_alerta_critica():
    alerta = EvaluadorPotenciaNegativaService.evaluar_alerta_potencia_negativa(_DISPOSITIVO, _lectura(-500.0))

    assert alerta is not None
    assert alerta.tipo_alerta == "POTENCIA_NEGATIVA"
    assert alerta.severidad == SeveridadAlerta.CRITICAL
    assert alerta.categoria == "POLARIDAD_TI"
    assert alerta.dispositivo_id == _DISPOSITIVO
    assert alerta.valor_medido == -500.0
    assert alerta.valor_umbral == -100.0


def test_potencia_negativa_dentro_del_margen_de_ruido_no_alerta():
    # Por encima de -100 W es ruido de medición: no hay alerta.
    assert EvaluadorPotenciaNegativaService.evaluar_alerta_potencia_negativa(_DISPOSITIVO, _lectura(-99.0)) is None
    assert EvaluadorPotenciaNegativaService.evaluar_alerta_potencia_negativa(_DISPOSITIVO, _lectura(-50.0)) is None


def test_potencia_exactamente_en_el_umbral_no_alerta():
    # El umbral es estricto (P < -100 W). La spec original decía "-100 W inclusive": desvío de límite.
    assert EvaluadorPotenciaNegativaService.evaluar_alerta_potencia_negativa(_DISPOSITIVO, _lectura(-100.0)) is None


def test_potencia_positiva_no_alerta():
    assert EvaluadorPotenciaNegativaService.evaluar_alerta_potencia_negativa(_DISPOSITIVO, _lectura(54840.0)) is None


def test_instalacion_generacion_fv_no_alerta_aunque_la_potencia_sea_negativa():
    alerta = EvaluadorPotenciaNegativaService.evaluar_alerta_potencia_negativa(
        _DISPOSITIVO, _lectura(-5000.0), tipo_instalacion="GENERACION_FV"
    )

    assert alerta is None


def test_sin_potencia_total_no_alerta():
    assert EvaluadorPotenciaNegativaService.evaluar_alerta_potencia_negativa(_DISPOSITIVO, _lectura(None)) is None


def test_anomalias_fases_delega_en_el_evaluador_dedicado():
    # evaluador_anomalias_fases.py no tiene lógica propia para POTENCIA_NEGATIVA: la expone como alias.
    lectura = _lectura(-500.0)

    via_fases = EvaluadorAnomaliasFasesService.evaluar_alerta_potencia_negativa(_DISPOSITIVO, lectura)
    directo = EvaluadorPotenciaNegativaService.evaluar_alerta_potencia_negativa(_DISPOSITIVO, lectura)

    assert via_fases is not None and directo is not None
    assert via_fases.tipo_alerta == directo.tipo_alerta == "POTENCIA_NEGATIVA"
    assert via_fases.valor_medido == directo.valor_medido


def test_persistencia_no_confirma_la_primera_lectura_negativa():
    # Diseño actual: un transitorio aislado no dispara alerta (1ra lectura = inicio del evento).
    filtro = FiltroPersistenciaTemporalService()
    cruda = EvaluadorPotenciaNegativaService.evaluar_alerta_potencia_negativa(_DISPOSITIVO, _lectura(-500.0))

    assert filtro.procesar_alerta(_DISPOSITIVO, cruda, categoria="POTENCIA_NEGATIVA", ahora=_T0) is None


def test_persistencia_confirma_en_la_segunda_lectura_consecutiva():
    filtro = FiltroPersistenciaTemporalService()
    t1 = _T0
    t2 = _T0 + timedelta(seconds=10)
    cruda1 = EvaluadorPotenciaNegativaService.evaluar_alerta_potencia_negativa(_DISPOSITIVO, _lectura(-500.0, t1))
    cruda2 = EvaluadorPotenciaNegativaService.evaluar_alerta_potencia_negativa(_DISPOSITIVO, _lectura(-480.0, t2))

    filtro.procesar_alerta(_DISPOSITIVO, cruda1, categoria="POTENCIA_NEGATIVA", ahora=t1)
    confirmada = filtro.procesar_alerta(_DISPOSITIVO, cruda2, categoria="POTENCIA_NEGATIVA", ahora=t2)

    assert confirmada is not None
    assert confirmada.tipo_alerta == "POTENCIA_NEGATIVA"
    assert confirmada.severidad == SeveridadAlerta.CRITICAL


def test_lectura_normal_resetea_la_persistencia():
    # Si la potencia vuelve a ser normal, el próximo negativo empieza de cero (no hereda la racha).
    filtro = FiltroPersistenciaTemporalService()
    t1 = _T0
    t2 = _T0 + timedelta(seconds=10)
    t3 = _T0 + timedelta(seconds=20)
    negativa = EvaluadorPotenciaNegativaService.evaluar_alerta_potencia_negativa(_DISPOSITIVO, _lectura(-500.0, t1))
    normal = EvaluadorPotenciaNegativaService.evaluar_alerta_potencia_negativa(_DISPOSITIVO, _lectura(1000.0, t2))
    negativa_otra_vez = EvaluadorPotenciaNegativaService.evaluar_alerta_potencia_negativa(
        _DISPOSITIVO, _lectura(-500.0, t3)
    )

    filtro.procesar_alerta(_DISPOSITIVO, negativa, categoria="POTENCIA_NEGATIVA", ahora=t1)
    filtro.procesar_alerta(_DISPOSITIVO, normal, categoria="POTENCIA_NEGATIVA", ahora=t2)
    resultado = filtro.procesar_alerta(_DISPOSITIVO, negativa_otra_vez, categoria="POTENCIA_NEGATIVA", ahora=t3)

    assert resultado is None

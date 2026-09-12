"""tests/unit/test_diagnostico_fasorial.py."""

from datetime import datetime, timezone

from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
from src.domain.telemetria.servicios.analizador_fasorial import AnalizadorFasorialService
from src.domain.telemetria.value_objects import Corriente, PotenciaActiva, PotenciaReactiva, Tension


def test_analizador_fasorial_fase_balanceada():
    fase = MedicionFase(
        tension=Tension(220.0),
        corriente=Corriente(10.0),
        potencia_activa=PotenciaActiva(2134.0),
        potencia_reactiva=PotenciaReactiva(536.0),
    )
    eval_fase = AnalizadorFasorialService.evaluar_fase(fase)
    assert eval_fase.fp_original is not None
    assert eval_fase.fp_original >= 0.95
    assert eval_fase.rotacion_optima_sugerida == "0°"


def test_analizador_fasorial_detecta_desfasaje_fase_t():
    fase_t_anomala = MedicionFase(
        tension=Tension(221.0),
        corriente=Corriente(120.0),
        potencia_activa=PotenciaActiva(6432.0),
        potencia_reactiva=PotenciaReactiva(-27539.0),
    )
    eval_fase = AnalizadorFasorialService.evaluar_fase(fase_t_anomala)
    assert eval_fase.fp_original is not None
    assert eval_fase.fp_original < 0.30
    assert eval_fase.rotacion_optima_sugerida in ("+60°", "-120°")
    assert eval_fase.fp_con_rotacion_optima is not None
    assert eval_fase.fp_con_rotacion_optima >= 0.90


def test_analizador_fasorial_diagnostico_general():
    lectura = LecturaInstantanea(
        id=1,
        dispositivo_id="dev-test",
        registrado_en=datetime.now(timezone.utc),
        fase_r=MedicionFase(
            potencia_activa=PotenciaActiva(20000.0),
            potencia_reactiva=PotenciaReactiva(5000.0),
        ),
        fase_s=MedicionFase(
            potencia_activa=PotenciaActiva(16000.0),
            potencia_reactiva=PotenciaReactiva(16000.0),
        ),
        fase_t=MedicionFase(
            potencia_activa=PotenciaActiva(6000.0),
            potencia_reactiva=PotenciaReactiva(-27000.0),
        ),
    )
    diag = AnalizadorFasorialService.diagnosticar_lectura("dev-test", lectura)
    assert "desfasaje" in diag.diagnostico_general.lower() or "cruce" in diag.diagnostico_general.lower()
    assert "V_S" in diag.recomendacion_hardware or "V_T" in diag.recomendacion_hardware

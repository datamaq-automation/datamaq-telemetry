from scripts.diagnosticar_instalacion_ti import calcular_angulo_fp, diagnosticar_lectura
from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
from src.domain.telemetria.value_objects import (
    Corriente,
    FactorPotencia,
    PotenciaActiva,
    PotenciaReactiva,
    Tension,
)


def test_calcular_angulo_fp():
    assert calcular_angulo_fp(1.0) == 0.0
    assert round(calcular_angulo_fp(0.0), 1) == 90.0
    assert round(calcular_angulo_fp(0.85), 1) == 31.8


def test_diagnosticar_lectura_misma_fase():
    lectura = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-constituyentes",
        registrado_en=None,
        fase_r=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(286.6),
            potencia_activa=PotenciaActiva(1260.0),
            potencia_reactiva=PotenciaReactiva(-63000.0),
            factor_potencia=FactorPotencia(0.02),
        ),
        fase_s=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(286.5),
            potencia_activa=PotenciaActiva(53580.0),
            potencia_reactiva=PotenciaReactiva(33200.0),
            factor_potencia=FactorPotencia(0.85),
        ),
        fase_t=MedicionFase(tension=Tension(220.0), corriente=Corriente(0.0)),
        potencia_activa_total=PotenciaActiva(54840.0),
        potencia_reactiva_total=PotenciaReactiva(-29800.0),
        factor_potencia_total=FactorPotencia(0.44),
    )

    resultado = diagnosticar_lectura(lectura, fases_con_ti=["R", "S"])
    assert resultado.estado_general == "CRITICO"
    assert any("[CRÍTICO] TIs en la misma fase" in h for h in resultado.hallazgos)
    assert any("Reubicar el sensor toroidal" in r for r in resultado.recomendaciones)


def test_diagnosticar_lectura_normal():
    lectura = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-normal",
        registrado_en=None,
        fase_r=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(20.0),
            potencia_activa=PotenciaActiva(4180.0),
            potencia_reactiva=PotenciaReactiva(1300.0),
            factor_potencia=FactorPotencia(0.95),
        ),
        fase_s=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(20.0),
            potencia_activa=PotenciaActiva(4180.0),
            potencia_reactiva=PotenciaReactiva(1300.0),
            factor_potencia=FactorPotencia(0.95),
        ),
        fase_t=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(20.0),
            potencia_activa=PotenciaActiva(4180.0),
            potencia_reactiva=PotenciaReactiva(1300.0),
            factor_potencia=FactorPotencia(0.95),
        ),
        potencia_activa_total=PotenciaActiva(12540.0),
        potencia_reactiva_total=PotenciaReactiva(3900.0),
        factor_potencia_total=FactorPotencia(0.95),
    )

    resultado = diagnosticar_lectura(lectura, fases_con_ti=["R", "S", "T"])
    assert resultado.estado_general == "OK"
    assert "Parámetros fasoriales dentro de los rangos normales de operación." in resultado.hallazgos[0]


def test_diagnosticar_lectura_ti_invertido():
    lectura = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-inv",
        registrado_en=None,
        fase_r=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(20.0),
            potencia_activa=PotenciaActiva(-4180.0),
            factor_potencia=FactorPotencia(-0.95),
        ),
        fase_s=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(20.0),
            potencia_activa=PotenciaActiva(4180.0),
            factor_potencia=FactorPotencia(0.95),
        ),
        fase_t=MedicionFase(
            tension=Tension(220.0),
            corriente=Corriente(20.0),
            potencia_activa=PotenciaActiva(4180.0),
            factor_potencia=FactorPotencia(0.95),
        ),
    )

    resultado = diagnosticar_lectura(lectura, fases_con_ti=["R", "S", "T"])
    assert resultado.estado_general == "ADVERTENCIA"
    assert any("[ADVERTENCIA] TI Invertido" in h for h in resultado.hallazgos)

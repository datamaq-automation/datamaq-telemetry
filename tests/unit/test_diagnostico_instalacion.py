"""Tests unitarios para el servicio de diagnóstico metrológico de instalación."""

from datetime import datetime, timezone

import pytest

from src.application.dtos.telemetria_dto import LecturaInstantaneaDTO
from src.application.mappers.telemetria_mapper import TelemetriaMapper
from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
from src.domain.telemetria.servicios.evaluador_diagnostico_instalacion import (
    EvaluadorDiagnosticoInstalacionService,
)
from src.domain.telemetria.value_objects import (
    Corriente,
    EstadoMetrologicoLectura,
    FactorPotencia,
    PotenciaActiva,
    PotenciaReactiva,
    Tension,
)


def _crear_lectura_balanceada() -> LecturaInstantanea:
    fase_base = MedicionFase(
        tension=Tension(220.0),
        corriente=Corriente(20.0),
        potencia_activa=PotenciaActiva(4000.0),
        potencia_reactiva=PotenciaReactiva(1000.0),
        factor_potencia=FactorPotencia(0.97),
    )
    return LecturaInstantanea(
        id=1,
        dispositivo_id="dev-normal",
        registrado_en=datetime.now(timezone.utc),
        fase_r=fase_base,
        fase_s=fase_base,
        fase_t=fase_base,
    )


def _crear_lectura_constituyentes() -> LecturaInstantanea:
    fase_r = MedicionFase(
        tension=Tension(219.0),
        corriente=Corriente(287.0),
        potencia_activa=PotenciaActiva(2500.0),
        potencia_reactiva=PotenciaReactiva(-62800.0),
        factor_potencia=FactorPotencia(0.04),
    )
    fase_s = MedicionFase(
        tension=Tension(219.0),
        corriente=Corriente(287.0),
        potencia_activa=PotenciaActiva(59000.0),
        potencia_reactiva=PotenciaReactiva(20000.0),
        factor_potencia=FactorPotencia(0.94),
    )
    fase_t = MedicionFase(
        tension=Tension(220.0),
        corriente=Corriente(0.0),
        potencia_activa=PotenciaActiva(0.0),
        potencia_reactiva=PotenciaReactiva(0.0),
        factor_potencia=FactorPotencia(0.0),
    )
    return LecturaInstantanea(
        id=2,
        dispositivo_id="D48C49F035A8",
        registrado_en=datetime.now(timezone.utc),
        fase_r=fase_r,
        fase_s=fase_s,
        fase_t=fase_t,
    )


def test_diagnostico_instalacion_balanceada():
    lectura = _crear_lectura_balanceada()
    diag = EvaluadorDiagnosticoInstalacionService.evaluar_diagnostico(lectura, fases_con_ti=["R", "S", "T"])
    assert diag.estado_metrologico == EstadoMetrologicoLectura.CONFIABLE
    assert diag.fases_validas == ("R", "S", "T")
    assert diag.fases_comprometidas == ()
    assert diag.anomalias_detectadas == ()
    assert diag.potencia_estimada_simetrica_w is None


def test_diagnostico_instalacion_ti_duplicado_y_desconectado():
    lectura = _crear_lectura_constituyentes()
    diag = EvaluadorDiagnosticoInstalacionService.evaluar_diagnostico(
        lectura,
        fases_con_ti=["R", "S", "T"],
        dispositivo_id="D48C49F035A8",
    )
    assert diag.estado_metrologico == EstadoMetrologicoLectura.DEGRADADO
    assert diag.fases_validas == ("S",)
    assert set(diag.fases_comprometidas) == {"R", "T"}
    assert diag.potencia_estimada_simetrica_w == pytest.approx(177000.0, rel=1e-2)
    assert diag.accion_correctiva_sugerida is not None
    assert "Reubicar sensor toroidal del canal R" in diag.accion_correctiva_sugerida
    assert "Fase T" in diag.accion_correctiva_sugerida


def test_diagnostico_instalacion_no_confiable(monkeypatch):
    lectura = _crear_lectura_balanceada()
    monkeypatch.setattr(
        EvaluadorDiagnosticoInstalacionService,
        "_identificar_comprometidas_y_anomalias",
        classmethod(
            lambda cls, dev_id, lect, fases: ({"R", "S", "T"}, ["ANOMALIA_CRITICA_TOTAL"], ["Revisar conexionado"])
        ),
    )
    diag = EvaluadorDiagnosticoInstalacionService.evaluar_diagnostico(
        lectura,
        fases_con_ti=["R", "S", "T"],
    )
    assert diag.estado_metrologico == EstadoMetrologicoLectura.NO_CONFIABLE
    assert diag.fases_validas == ()
    assert set(diag.fases_comprometidas) == {"R", "S", "T"}


def test_telemetria_mapper_incluye_diagnostico_instalacion():
    lectura = _crear_lectura_constituyentes()
    diag = EvaluadorDiagnosticoInstalacionService.evaluar_diagnostico(lectura, fases_con_ti=["R", "S", "T"])
    lectura_con_diag = LecturaInstantanea(
        id=lectura.id,
        dispositivo_id=lectura.dispositivo_id,
        registrado_en=lectura.registrado_en,
        fase_r=lectura.fase_r,
        fase_s=lectura.fase_s,
        fase_t=lectura.fase_t,
        diagnostico_instalacion=diag,
    )
    dto: LecturaInstantaneaDTO = TelemetriaMapper.instantanea_to_dto(lectura_con_diag)
    assert dto.diagnostico_instalacion is not None
    assert dto.diagnostico_instalacion.estado_metrologico == EstadoMetrologicoLectura.DEGRADADO
    assert dto.diagnostico_instalacion.fases_validas == ["S"]
    assert set(dto.diagnostico_instalacion.fases_comprometidas) == {"R", "T"}
    assert dto.diagnostico_instalacion.potencia_estimada_simetrica_w == pytest.approx(177000.0, rel=1e-2)

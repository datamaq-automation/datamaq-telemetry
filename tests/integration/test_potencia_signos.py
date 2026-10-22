"""tests/integration/test_potencia_signos.py - Capa 1: Deteccion de potencia negativa."""

from datetime import datetime, timezone

from src.domain.telemetria.servicios.evaluador_anomalias_fases import (
    EvaluadorAnomaliasFasesService,
)
from src.domain.telemetria.value_objects import SeveridadAlerta


class MockPotencia:
    """Mock de Potencia para tests."""

    def __init__(self, vatios=0.0, var=0.0, va=0.0):
        self.vatios = vatios
        self.var = var
        self.va = va


class MockMedicionFase:
    """Mock de MedicionFase."""

    def __init__(self):
        self.potencia_activa = MockPotencia(vatios=1000.0)
        self.potencia_reactiva = MockPotencia(var=500.0)
        self.potencia_aparente = MockPotencia(va=1150.0)


class MockLectura:
    """Mock de LecturaInstantanea."""

    def __init__(self, p_total=3000.0, registrado_en=None):
        self.potencia_activa_total = MockPotencia(vatios=p_total)
        self.potencia_reactiva_total = MockPotencia(var=1500.0)
        self.potencia_aparente_total = MockPotencia(va=3350.0)
        self.registrado_en = registrado_en or datetime.now(timezone.utc)
        self.fase_r = MockMedicionFase()
        self.fase_s = MockMedicionFase()
        self.fase_t = MockMedicionFase()


def test_potencia_negativa_genera_alerta_critical():
    """Verifica que P < -100 W genera alerta CRITICAL."""
    lectura = MockLectura(p_total=-150.0)
    alerta = EvaluadorAnomaliasFasesService.evaluar_alerta_potencia_negativa(
        dispositivo_id="dev-trafo2-369",
        lectura=lectura,  # type: ignore
        tipo_instalacion="CONSUMO",
        umbral_p_minima_w=-100.0,
    )

    assert alerta is not None
    assert alerta.tipo_alerta == "POTENCIA_NEGATIVA"
    assert alerta.severidad == SeveridadAlerta.CRITICAL
    assert alerta.valor_medido == -150.0
    assert alerta.categoria == "POLARIDAD_TI"


def test_potencia_negativa_dentro_margen_sin_alerta():
    """Verifica que -99 W (dentro de -100) NO genera alerta."""
    lectura = MockLectura(p_total=-99.0)
    alerta = EvaluadorAnomaliasFasesService.evaluar_alerta_potencia_negativa(
        dispositivo_id="dev-trafo2-369",
        lectura=lectura,  # type: ignore
        tipo_instalacion="CONSUMO",
        umbral_p_minima_w=-100.0,
    )

    assert alerta is None


def test_potencia_positiva_sin_alerta():
    """Verifica que P > 0 NO genera alerta."""
    lectura = MockLectura(p_total=3000.0)
    alerta = EvaluadorAnomaliasFasesService.evaluar_alerta_potencia_negativa(
        dispositivo_id="dev-trafo2-369",
        lectura=lectura,  # type: ignore
        tipo_instalacion="CONSUMO",
        umbral_p_minima_w=-100.0,
    )

    assert alerta is None


def test_potencia_negativa_generacion_fv_sin_alerta():
    """Verifica que P < 0 en GENERACION_FV NO genera alerta (valido)."""
    lectura = MockLectura(p_total=-150.0)
    alerta = EvaluadorAnomaliasFasesService.evaluar_alerta_potencia_negativa(
        dispositivo_id="dev-solar-001",
        lectura=lectura,  # type: ignore
        tipo_instalacion="GENERACION_FV",
        umbral_p_minima_w=-100.0,
    )

    assert alerta is None


def test_potencia_negativa_limite_exacto():
    """Verifica que -100 W (limite exacto) NO genera alerta."""
    lectura = MockLectura(p_total=-100.0)
    alerta = EvaluadorAnomaliasFasesService.evaluar_alerta_potencia_negativa(
        dispositivo_id="dev-trafo2-369",
        lectura=lectura,  # type: ignore
        tipo_instalacion="CONSUMO",
        umbral_p_minima_w=-100.0,
    )

    assert alerta is None

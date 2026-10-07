"""Tests para validación de granularidad de telemetría."""

import pytest

from src.domain.telemetria.value_objects import (
    GranularidadTelemetria,
    obtener_default_granularidad,
    validar_granularidad,
)


class TestGranularidadTelemetria:
    """Tests para el enum GranularidadTelemetria."""

    def test_enum_values(self) -> None:
        """Verifica los valores del enum."""
        assert GranularidadTelemetria.CINCO_MINUTOS.value == "5m"
        assert GranularidadTelemetria.QUINCE_MINUTOS.value == "15m"
        assert GranularidadTelemetria.TREINTA_MINUTOS.value == "30m"
        assert GranularidadTelemetria.UNA_HORA.value == "1h"
        assert GranularidadTelemetria.UN_DIA.value == "1d"


class TestObtenerDefaultGranularidad:
    """Tests para obtener default según período."""

    def test_default_24h(self) -> None:
        """Default para 24h es 5m."""
        assert obtener_default_granularidad("24h") == GranularidadTelemetria.CINCO_MINUTOS

    def test_default_7d(self) -> None:
        """Default para 7d es 30m."""
        assert obtener_default_granularidad("7d") == GranularidadTelemetria.TREINTA_MINUTOS

    def test_default_30d(self) -> None:
        """Default para 30d es 1h."""
        assert obtener_default_granularidad("30d") == GranularidadTelemetria.UNA_HORA

    def test_default_periodo_invalido(self) -> None:
        """Lanza ValueError para período inválido."""
        with pytest.raises(ValueError, match="Período no válido"):
            obtener_default_granularidad("60d")  # type: ignore


class TestValidarGranularidad:
    """Tests para validación de granularidad por período."""

    # Validaciones correctas para 24h
    def test_valida_5m_en_24h(self) -> None:
        """5m es válido para 24h."""
        resultado = validar_granularidad("5m", "24h")
        assert resultado == GranularidadTelemetria.CINCO_MINUTOS

    def test_valida_15m_en_24h(self) -> None:
        """15m es válido para 24h."""
        resultado = validar_granularidad("15m", "24h")
        assert resultado == GranularidadTelemetria.QUINCE_MINUTOS

    def test_valida_30m_en_24h(self) -> None:
        """30m es válido para 24h."""
        resultado = validar_granularidad("30m", "24h")
        assert resultado == GranularidadTelemetria.TREINTA_MINUTOS

    # Validaciones correctas para 7d
    def test_valida_15m_en_7d(self) -> None:
        """15m es válido para 7d."""
        resultado = validar_granularidad("15m", "7d")
        assert resultado == GranularidadTelemetria.QUINCE_MINUTOS

    def test_valida_30m_en_7d(self) -> None:
        """30m es válido para 7d."""
        resultado = validar_granularidad("30m", "7d")
        assert resultado == GranularidadTelemetria.TREINTA_MINUTOS

    def test_valida_1h_en_7d(self) -> None:
        """1h es válido para 7d."""
        resultado = validar_granularidad("1h", "7d")
        assert resultado == GranularidadTelemetria.UNA_HORA

    # Validaciones correctas para 30d
    def test_valida_1h_en_30d(self) -> None:
        """1h es válido para 30d."""
        resultado = validar_granularidad("1h", "30d")
        assert resultado == GranularidadTelemetria.UNA_HORA

    def test_valida_1d_en_30d(self) -> None:
        """1d es válido para 30d."""
        resultado = validar_granularidad("1d", "30d")
        assert resultado == GranularidadTelemetria.UN_DIA

    # Validaciones inválidas
    def test_invalida_1h_en_24h(self) -> None:
        """1h NO es válido para 24h."""
        with pytest.raises(ValueError, match="no válida para período"):
            validar_granularidad("1h", "24h")

    def test_invalida_5m_en_7d(self) -> None:
        """5m NO es válido para 7d."""
        with pytest.raises(ValueError, match="no válida para período"):
            validar_granularidad("5m", "7d")

    def test_invalida_1d_en_7d(self) -> None:
        """1d NO es válido para 7d."""
        with pytest.raises(ValueError, match="no válida para período"):
            validar_granularidad("1d", "7d")

    def test_granularidad_no_reconocida(self) -> None:
        """Lanza ValueError para granularidad no válida."""
        with pytest.raises(ValueError, match="no reconocida"):
            validar_granularidad("2m", "24h")

    def test_periodo_invalido(self) -> None:
        """Lanza ValueError para período inválido."""
        with pytest.raises(ValueError, match="Período no válido"):
            validar_granularidad("5m", "60d")  # type: ignore

    # Aceptar enum directamente
    def test_valida_enum_directamente(self) -> None:
        """Puede aceptar GranularidadTelemetria enum directamente."""
        resultado = validar_granularidad(GranularidadTelemetria.CINCO_MINUTOS, "24h")
        assert resultado == GranularidadTelemetria.CINCO_MINUTOS

"""Tests para EjecutarDiagnosticoTIApplicationService."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from src.application.services.diagnostico_ti_app_service import (
    DiagnosticoTIResultDTO,
    EjecutarDiagnosticoTIApplicationService,
)
from src.domain.telemetria.value_objects import CandidatoTI


class TestEjecutarDiagnosticoTIApplicationService:
    """Tests del ApplicationService (orquestador)."""

    def test_ejecutar_con_datos(self) -> None:
        """Ejecutar diagnóstico con datos disponibles."""
        # Mock repository
        repo_mock = MagicMock()
        repo_mock.obtener_mediciones_dispositivo.return_value = [
            {
                "p_r": 1000.0,
                "p_s": 1000.0,
                "p_t": 0.0,
                "q_r": 500.0,
                "q_s": 500.0,
                "q_t": 0.0,
                "s_r": 1118.034,
                "s_s": 1118.034,
                "s_t": 0.0,
                "fp_r": 0.894,
                "fp_s": 0.894,
                "fp_t": 0.0,
            }
        ]

        service = EjecutarDiagnosticoTIApplicationService(repo_mock)
        result = service.ejecutar(
            dispositivo_id="abc123",
            fases_con_ti=("R", "S", "T"),
            periodo_horas=24,
        )

        assert result.dispositivo_id == "abc123"
        assert result.registros_analizados == 1
        assert result.error is None
        assert len(result.candidatos) > 0
        assert result.candidatos[0].score > 0.90

    def test_ejecutar_sin_datos(self) -> None:
        """Ejecutar diagnóstico sin datos retorna error."""
        repo_mock = MagicMock()
        repo_mock.obtener_mediciones_dispositivo.return_value = []

        service = EjecutarDiagnosticoTIApplicationService(repo_mock)
        result = service.ejecutar(
            dispositivo_id="abc123",
            fases_con_ti=("R", "S", "T"),
        )

        assert result.registros_analizados == 0
        assert result.error is not None
        assert len(result.candidatos) == 0

    def test_convertir_tipos_decimal_a_float(self) -> None:
        """Convertir Decimal (de BD) a float."""
        registros_db = [
            {
                "p_r": Decimal("1000.50"),
                "q_r": Decimal("500.25"),
                "s_r": Decimal("1118.034"),
            }
        ]

        registros_convertidos = EjecutarDiagnosticoTIApplicationService._convertir_tipos(registros_db)

        assert isinstance(registros_convertidos[0]["p_r"], float)
        assert registros_convertidos[0]["p_r"] == 1000.50
        assert registros_convertidos[0]["q_r"] == 500.25

    def test_convertir_tipos_preserva_none(self) -> None:
        """Convertir tipos preserva None."""
        registros_db = [{"p_r": 1000.0, "q_r": None, "s_r": Decimal("1118.034")}]

        registros_convertidos = EjecutarDiagnosticoTIApplicationService._convertir_tipos(registros_db)

        assert registros_convertidos[0]["q_r"] is None
        assert registros_convertidos[0]["s_r"] == 1118.034

    def test_resultado_dto_to_dict(self) -> None:
        """Serializar DTO a dict."""
        candidatos = [
            CandidatoTI(
                orden_fases=("R", "S", "T"),
                invertido=False,
                score=0.9876,
                justificacion="OK",
            )
        ]

        result = DiagnosticoTIResultDTO(
            dispositivo_id="abc123",
            periodo_horas=24,
            registros_analizados=100,
            candidatos=candidatos,
            error=None,
        )

        d = result.to_dict()
        assert d["dispositivo_id"] == "abc123"
        assert d["registros_analizados"] == 100
        assert d["error"] is None
        assert len(d["candidatos"]) == 1
        assert d["candidatos"][0]["score"] == 0.9876
        assert d["candidatos"][0]["orden_fases"] == ["R", "S", "T"]

    def test_resultado_dto_con_error(self) -> None:
        """DTO con error."""
        result = DiagnosticoTIResultDTO(
            dispositivo_id="abc123",
            periodo_horas=24,
            registros_analizados=0,
            candidatos=[],
            error="Sin datos",
        )

        d = result.to_dict()
        assert d["error"] == "Sin datos"
        assert len(d["candidatos"]) == 0

    def test_bifasico(self) -> None:
        """Ejecutar para bifásico (R, S)."""
        repo_mock = MagicMock()
        repo_mock.obtener_mediciones_dispositivo.return_value = [
            {
                "p_r": 1000.0,
                "p_s": 1000.0,
                "p_t": 0.0,
                "q_r": 500.0,
                "q_s": 500.0,
                "q_t": 0.0,
                "s_r": 1118.034,
                "s_s": 1118.034,
                "s_t": 0.0,
                "fp_r": 0.894,
                "fp_s": 0.894,
                "fp_t": 0.0,
            }
        ]

        service = EjecutarDiagnosticoTIApplicationService(repo_mock)
        result = service.ejecutar(
            dispositivo_id="abc123",
            fases_con_ti=("R", "S"),
            periodo_horas=24,
        )

        assert result.error is None
        assert len(result.candidatos) <= 4  # max 2 órdenes x 2 polaridades

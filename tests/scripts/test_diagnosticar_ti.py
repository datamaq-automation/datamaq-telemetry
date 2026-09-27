"""Tests para scripts/diagnosticar_ti.py."""

from __future__ import annotations

from scripts.diagnosticar_ti import (
    MedicionFase,
    aplicar_transformacion_ti,
    calcular_fp_teorico,
    calcular_s_teorica,
    error_coherencia_fp,
    error_coherencia_s,
    rankear_candidatos,
)


class TestCalculosFasorial:
    """Tests de cálculos de potencia aparente y factor de potencia."""

    def test_s_teorica_calculo_basico(self) -> None:
        """S = √(P² + Q²): caso 3-4-5."""
        s = calcular_s_teorica(3.0, 4.0)
        assert s == 5.0

    def test_s_teorica_sin_reactiva(self) -> None:
        """S = P si Q = 0."""
        s = calcular_s_teorica(10.0, 0.0)
        assert s == 10.0

    def test_fp_teorico_basico(self) -> None:
        """FP = P/S: caso 0.8."""
        fp = calcular_fp_teorico(80.0, 100.0)
        assert fp == 0.8

    def test_error_coherencia_s_cero(self) -> None:
        """Error S cuando S teórica es cero."""
        err = error_coherencia_s(0.0, 0.0, 10.0)
        assert err == 0.0

    def test_error_coherencia_fp_cero(self) -> None:
        """Error FP cuando ambas son cero."""
        err = error_coherencia_fp(0.0, 0.0, 0.0)
        assert err == 0.0


class TestTransformacionTI:
    """Tests de aplicación de transformaciones de orden/polaridad."""

    def test_transformacion_identidad(self) -> None:
        """Orden [R,S,T] sin inversión debe ser identidad."""
        med_r = MedicionFase(p=100.0, q=50.0, s=120.0, fp=0.8)
        med_s = MedicionFase(p=100.0, q=50.0, s=120.0, fp=0.8)
        med_t = MedicionFase(p=0.0, q=0.0, s=0.0, fp=0.0)

        resultado = aplicar_transformacion_ti(med_r, med_s, med_t, ["R", "S", "T"], False)

        assert resultado["R"].p == 100.0
        assert resultado["R"].q == 50.0
        assert resultado["S"].p == 100.0
        assert resultado["S"].q == 50.0

    def test_transformacion_inversion(self) -> None:
        """Inversión debe negar Q."""
        med_r = MedicionFase(p=100.0, q=50.0, s=120.0, fp=0.8)
        med_s = MedicionFase(p=100.0, q=50.0, s=120.0, fp=0.8)
        med_t = MedicionFase(p=0.0, q=0.0, s=0.0, fp=0.0)

        resultado = aplicar_transformacion_ti(med_r, med_s, med_t, ["R", "S", "T"], True)

        assert resultado["R"].p == 100.0
        assert resultado["R"].q == -50.0

    def test_transformacion_reorden(self) -> None:
        """Reordenar [S,R,T] debe intercambiar R y S."""
        med_r = MedicionFase(p=100.0, q=50.0, s=120.0, fp=0.8)
        med_s = MedicionFase(p=200.0, q=60.0, s=230.0, fp=0.87)
        med_t = MedicionFase(p=0.0, q=0.0, s=0.0, fp=0.0)

        resultado = aplicar_transformacion_ti(med_r, med_s, med_t, ["S", "R", "T"], False)

        assert resultado["R"].p == 200.0
        assert resultado["S"].p == 100.0


class TestRankingCandidatos:
    """Tests del ranking de candidatos por coherencia."""

    def test_ranking_coherencia_maxima(self) -> None:
        """Candidato con coherencia perfecta debe estar en top."""
        registros = [
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

        candidatos = rankear_candidatos(registros, ["R", "S"])
        assert len(candidatos) > 0
        assert candidatos[0].score > 0.90

    def test_ranking_bifasico(self) -> None:
        """Ranking de bifásico debe tener máximo 4 candidatos (2 órdenes × 2 polaridades)."""
        registros = [
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

        candidatos = rankear_candidatos(registros, ["R", "S"])
        assert len(candidatos) <= 4

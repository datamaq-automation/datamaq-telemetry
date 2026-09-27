"""Tests para Value Objects de diagnóstico de TI."""

from __future__ import annotations

import pytest

from src.domain.telemetria.value_objects import CandidatoTI, MedicionFase


class TestMedicionFase:
    """Tests de MedicionFase (value object de medición de fase)."""

    def test_creacion_basica(self) -> None:
        """Crear medición con valores nominales."""
        med = MedicionFase(p=1000.0, q=500.0, s=1118.0, fp=0.89)
        assert med.p == 1000.0
        assert med.q == 500.0
        assert med.s == 1118.0
        assert med.fp == 0.89

    def test_creacion_parcial(self) -> None:
        """Crear medición con solo P y Q."""
        med = MedicionFase(p=1000.0, q=500.0)
        assert med.p == 1000.0
        assert med.q == 500.0
        assert med.s is None
        assert med.fp is None

    def test_creacion_vacia(self) -> None:
        """Crear medición vacía (todos None)."""
        med = MedicionFase()
        assert med.p is None
        assert med.q is None
        assert med.s is None
        assert med.fp is None

    def test_frozen_dataclass(self) -> None:
        """MedicionFase es un frozen dataclass (validable por type checker)."""
        med = MedicionFase(p=1000.0, q=500.0)
        med2 = MedicionFase(p=med.p, q=med.q)
        assert med == med2

    def test_serializable_dict(self) -> None:
        """MedicionFase puede convertirse a dict."""
        med = MedicionFase(p=1000.0, q=500.0, s=1118.0, fp=0.89)
        d = {
            "p": med.p,
            "q": med.q,
            "s": med.s,
            "fp": med.fp,
        }
        assert d["p"] == 1000.0
        assert d["fp"] == 0.89

    def test_negativo_permitido(self) -> None:
        """Q puede ser negativo (capacitivo)."""
        med = MedicionFase(p=1000.0, q=-500.0)
        assert med.q == -500.0


class TestCandidatoTI:
    """Tests de CandidatoTI (resultado de ranking)."""

    def test_creacion_basica(self) -> None:
        """Crear candidato con orden R,S,T normal."""
        cand = CandidatoTI(
            orden_fases=("R", "S", "T"),
            invertido=False,
            score=0.95,
            justificacion="Coherencia alta",
        )
        assert cand.orden_fases == ("R", "S", "T")
        assert cand.invertido is False
        assert cand.score == 0.95

    def test_creacion_bifasico(self) -> None:
        """Crear candidato bifásico."""
        cand = CandidatoTI(
            orden_fases=("R", "S"),
            invertido=True,
            score=0.42,
            justificacion="Bajo",
        )
        assert len(cand.orden_fases) == 2

    def test_posicion_sin_inversion(self) -> None:
        """Método posicion() sin inversión."""
        cand = CandidatoTI(
            orden_fases=("R", "S", "T"),
            invertido=False,
            score=0.9,
            justificacion="OK",
        )
        assert cand.posicion() == "R,S,T"

    def test_posicion_con_inversion(self) -> None:
        """Método posicion() con inversión."""
        cand = CandidatoTI(
            orden_fases=("S", "R", "T"),
            invertido=True,
            score=0.5,
            justificacion="OK",
        )
        assert cand.posicion() == "S,R,T (INV)"

    def test_score_limite_minimo(self) -> None:
        """Score 0.0 es válido."""
        cand = CandidatoTI(
            orden_fases=("R", "S", "T"),
            invertido=False,
            score=0.0,
            justificacion="Peor posible",
        )
        assert cand.score == 0.0

    def test_score_limite_maximo(self) -> None:
        """Score 1.0 es válido."""
        cand = CandidatoTI(
            orden_fases=("R", "S", "T"),
            invertido=False,
            score=1.0,
            justificacion="Perfecto",
        )
        assert cand.score == 1.0

    def test_score_fuera_rango_negativo(self) -> None:
        """Score < 0.0 rechazado."""
        with pytest.raises(ValueError, match="Score fuera de rango"):
            CandidatoTI(
                orden_fases=("R", "S", "T"),
                invertido=False,
                score=-0.1,
                justificacion="Inválido",
            )

    def test_score_fuera_rango_positivo(self) -> None:
        """Score > 1.0 rechazado."""
        with pytest.raises(ValueError, match="Score fuera de rango"):
            CandidatoTI(
                orden_fases=("R", "S", "T"),
                invertido=False,
                score=1.1,
                justificacion="Inválido",
            )

    def test_fase_invalida(self) -> None:
        """Fase que no sea R, S, T rechazada."""
        with pytest.raises(ValueError, match="Fase inválida"):
            CandidatoTI(
                orden_fases=("R", "X", "T"),
                invertido=False,
                score=0.5,
                justificacion="Inválido",
            )

    def test_orden_vacia(self) -> None:
        """Orden vacía rechazada."""
        with pytest.raises(ValueError, match="Orden de fases debe tener 1-3"):
            CandidatoTI(
                orden_fases=(),
                invertido=False,
                score=0.5,
                justificacion="Inválido",
            )

    def test_orden_cuatro_fases(self) -> None:
        """Orden con más de 3 fases rechazada."""
        with pytest.raises(ValueError, match="Orden de fases debe tener 1-3"):
            CandidatoTI(
                orden_fases=("R", "S", "T", "X"),
                invertido=False,
                score=0.5,
                justificacion="Inválido",
            )

    def test_frozen_dataclass(self) -> None:
        """CandidatoTI es un frozen dataclass (validable por type checker)."""
        cand = CandidatoTI(
            orden_fases=("R", "S", "T"),
            invertido=False,
            score=0.9,
            justificacion="OK",
        )
        cand2 = CandidatoTI(
            orden_fases=cand.orden_fases,
            invertido=cand.invertido,
            score=cand.score,
            justificacion=cand.justificacion,
        )
        assert cand == cand2

    def test_igualdad(self) -> None:
        """Dos candidatos con igual contenido son iguales."""
        cand1 = CandidatoTI(
            orden_fases=("R", "S", "T"),
            invertido=False,
            score=0.9,
            justificacion="OK",
        )
        cand2 = CandidatoTI(
            orden_fases=("R", "S", "T"),
            invertido=False,
            score=0.9,
            justificacion="OK",
        )
        assert cand1 == cand2

    def test_desigualdad_score(self) -> None:
        """Candidatos con score diferente no son iguales."""
        cand1 = CandidatoTI(
            orden_fases=("R", "S", "T"),
            invertido=False,
            score=0.9,
            justificacion="OK",
        )
        cand2 = CandidatoTI(
            orden_fases=("R", "S", "T"),
            invertido=False,
            score=0.8,
            justificacion="OK",
        )
        assert cand1 != cand2

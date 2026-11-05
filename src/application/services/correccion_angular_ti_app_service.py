"""src/application/services/correccion_angular_ti_app_service.py.

Application Service: candidatos de corrección angular por fase de TI (issue #63).

Orquesta el cálculo de dominio sobre dos mediciones de la misma fase bajo dos correcciones
distintas. No persiste nada y no elige un candidato: esa elección requiere Q o verificación
en campo y es decisión del dueño.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.telemetria.servicios.correccion_angular_ti import (
    candidatos_angulo_bruto,
    magnitud_angulo_deg,
)


@dataclass(frozen=True)
class MedicionFaseTI:
    """Tensión (V), corriente (I) y potencia activa (P) de una fase en una medición."""

    v: float
    i: float
    p: float


class CalcularCorreccionAngularTIApplicationService:
    """Devuelve, por fase, los ángulos brutos compatibles con dos mediciones.

    Una fase sin corrección en una de las dos mediciones usa alfa 0,0: es el mismo criterio que
    ``correccion_angular_fases`` vacío (sin rotación aplicada).
    """

    def __init__(self, tolerancia: float = 2.0) -> None:
        self.tolerancia = tolerancia

    def candidatos_por_fase(
        self,
        antes: dict[str, MedicionFaseTI],
        alpha_antes: dict[str, float],
        despues: dict[str, MedicionFaseTI],
        alpha_despues: dict[str, float],
    ) -> dict[str, list[float]]:
        """Candidatos de φ_bruto por fase presente en ambas mediciones, sin seleccionar ninguno."""
        resultado: dict[str, list[float]] = {}
        for fase in sorted(set(antes) & set(despues)):
            medicion_antes = antes[fase]
            medicion_despues = despues[fase]
            resultado[fase] = candidatos_angulo_bruto(
                magnitud_antes=magnitud_angulo_deg(medicion_antes.v, medicion_antes.i, medicion_antes.p),
                alpha_antes=alpha_antes.get(fase, 0.0),
                magnitud_despues=magnitud_angulo_deg(medicion_despues.v, medicion_despues.i, medicion_despues.p),
                alpha_despues=alpha_despues.get(fase, 0.0),
                tolerancia=self.tolerancia,
            )
        return resultado

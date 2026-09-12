"""src/domain/telemetria/servicios/analizador_fasorial.py."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase


@dataclass(frozen=True)
class EvaluacionRotacionFase:
    fp_original: float | None
    phi_deg_original: float | None
    potencia_activa_w: float | None
    potencia_reactiva_var: float | None
    rotacion_optima_sugerida: str | None
    fp_con_rotacion_optima: float | None
    p_con_rotacion_optima_w: float | None
    q_con_rotacion_optima_var: float | None
    rotaciones_evaluadas: dict[str, dict[str, float]]


@dataclass(frozen=True)
class DiagnosticoFasorialRed:
    dispositivo_id: str
    evaluado_en: datetime
    fase_r: EvaluacionRotacionFase
    fase_s: EvaluacionRotacionFase
    fase_t: EvaluacionRotacionFase
    diagnostico_general: str
    recomendacion_hardware: str


class AnalizadorFasorialService:
    """Servicio de dominio puro para simular y evaluar rotaciones/desfasajes fasoriales."""

    ANGULOS_PRUEBA: tuple[int, ...] = (-120, -60, 60, 120, 180)

    @classmethod
    def evaluar_fase(cls, fase: MedicionFase) -> EvaluacionRotacionFase:
        p = fase.potencia_activa.vatios if fase.potencia_activa else None
        q = fase.potencia_reactiva.var if fase.potencia_reactiva else None

        if p is None or q is None:
            return EvaluacionRotacionFase(
                fp_original=None,
                phi_deg_original=None,
                potencia_activa_w=None,
                potencia_reactiva_var=None,
                rotacion_optima_sugerida=None,
                fp_con_rotacion_optima=None,
                p_con_rotacion_optima_w=None,
                q_con_rotacion_optima_var=None,
                rotaciones_evaluadas={},
            )

        s = math.sqrt(p**2 + q**2)
        fp_orig = round(p / s, 3) if s > 0 else 0.0
        phi_orig_rad = math.atan2(q, p)
        phi_orig_deg = round(math.degrees(phi_orig_rad), 1)

        evaluadas: dict[str, dict[str, float]] = {
            "0°": {
                "fp": fp_orig,
                "p_w": round(p, 1),
                "q_var": round(q, 1),
                "phi_deg": phi_orig_deg,
            }
        }

        mejor_shift: int | None = None
        mejor_fp = fp_orig
        mejor_p = p
        mejor_q = q

        for shift in cls.ANGULOS_PRUEBA:
            phi_rot_rad = phi_orig_rad + math.radians(shift)
            p_rot = s * math.cos(phi_rot_rad)
            q_rot = s * math.sin(phi_rot_rad)
            fp_rot = round(p_rot / s, 3) if s > 0 else 0.0
            phi_rot_deg = round(math.degrees(phi_rot_rad), 1)

            clave = f"{shift:+d}°"
            evaluadas[clave] = {
                "fp": fp_rot,
                "p_w": round(p_rot, 1),
                "q_var": round(q_rot, 1),
                "phi_deg": phi_rot_deg,
            }

            # Criterio de optimización: FP inductivo alto (> 0.85 y P > 0)
            if fp_rot > mejor_fp and p_rot > 0:
                mejor_fp = fp_rot
                mejor_shift = shift
                mejor_p = p_rot
                mejor_q = q_rot

        rotacion_sug = f"{mejor_shift:+d}°" if mejor_shift is not None else "0°"

        return EvaluacionRotacionFase(
            fp_original=fp_orig,
            phi_deg_original=phi_orig_deg,
            potencia_activa_w=round(p, 1),
            potencia_reactiva_var=round(q, 1),
            rotacion_optima_sugerida=rotacion_sug,
            fp_con_rotacion_optima=round(mejor_fp, 3),
            p_con_rotacion_optima_w=round(mejor_p, 1),
            q_con_rotacion_optima_var=round(mejor_q, 1),
            rotaciones_evaluadas=evaluadas,
        )

    @classmethod
    def diagnosticar_lectura(cls, dispositivo_id: str, lectura: LecturaInstantanea) -> DiagnosticoFasorialRed:
        diag_r = cls.evaluar_fase(lectura.fase_r)
        diag_s = cls.evaluar_fase(lectura.fase_s)
        diag_t = cls.evaluar_fase(lectura.fase_t)

        anomalias = []
        if (diag_s.fp_original or 0) < 0.80 and diag_s.rotacion_optima_sugerida == "-60°":
            anomalias.append("Fase S con desfasaje cruzado de -60° (I_S midiendo contra tensión no colineal)")
        if (diag_t.fp_original or 0) < 0.50 and diag_t.rotacion_optima_sugerida in ("+60°", "-120°"):
            anomalias.append("Fase T con desfasaje fasorial de +60° / -120° (cruce de tensión V_T/V_S)")

        if anomalias:
            gen = "Desfasaje fasorial detectado en fases secundarias: " + "; ".join(anomalias)
            rec = "Verificar físicamente el orden de bornes de tensión V_S y V_T en el medidor, o intercambiar bornes de transformadores de corriente CT_S y CT_T."
        else:
            gen = "Fasores equilibrados y coherentes con carga trifásica normal."
            rec = "No se requiere intervención física en el cableado."

        return DiagnosticoFasorialRed(
            dispositivo_id=dispositivo_id,
            evaluado_en=lectura.registrado_en or datetime.now(timezone.utc),
            fase_r=diag_r,
            fase_s=diag_s,
            fase_t=diag_t,
            diagnostico_general=gen,
            recomendacion_hardware=rec,
        )

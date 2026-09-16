"""src/domain/telemetria/servicios/analizador_fasorial.py."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
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
    tension_v: float | None = None
    corriente_a: float | None = None
    angulo_fasorial_grados: float | None = None
    tc_invertido_180: bool = False
    estado_ti: str = "CORRECTO"


@dataclass(frozen=True)
class DiagnosticoFasorialRed:
    dispositivo_id: str
    evaluado_en: datetime
    fase_r: EvaluacionRotacionFase
    fase_s: EvaluacionRotacionFase
    fase_t: EvaluacionRotacionFase
    diagnostico_general: str
    recomendacion_hardware: str
    secuencia_fases: str = "DIRECTA"
    rotacion_correcta: bool = True
    alertas_fasoriales: tuple[str, ...] = ()


class AnalizadorFasorialService:
    """Servicio de dominio puro para simular y evaluar rotaciones/desfasajes fasoriales."""

    ANGULOS_PRUEBA: tuple[int, ...] = (-120, -60, 60, 120, 180)

    @staticmethod
    def _evaluar_rotaciones_optimas(
        p: float, q: float, s: float, fp_orig: float, phi_orig_rad: float, phi_orig_deg: float
    ) -> tuple[dict[str, dict[str, float]], float, float, float, str]:
        evaluadas: dict[str, dict[str, float]] = {
            "0°": {"fp": fp_orig, "p_w": round(p, 1), "q_var": round(q, 1), "phi_deg": phi_orig_deg}
        }
        mejor_shift: int | None = None
        mejor_fp, mejor_p, mejor_q = fp_orig, p, q

        for shift in AnalizadorFasorialService.ANGULOS_PRUEBA:
            phi_rot_rad = phi_orig_rad + math.radians(shift)
            p_rot, q_rot = s * math.cos(phi_rot_rad), s * math.sin(phi_rot_rad)
            fp_rot = round(p_rot / s, 3) if s > 0 else 0.0
            phi_rot_deg = round(math.degrees(phi_rot_rad), 1)

            evaluadas[f"{shift:+d}°"] = {
                "fp": fp_rot,
                "p_w": round(p_rot, 1),
                "q_var": round(q_rot, 1),
                "phi_deg": phi_rot_deg,
            }
            if fp_rot > mejor_fp and p_rot > 0:
                mejor_fp, mejor_shift, mejor_p, mejor_q = fp_rot, shift, p_rot, q_rot

        rotacion_sug = f"{mejor_shift:+d}°" if mejor_shift is not None else "0°"
        return evaluadas, mejor_fp, mejor_p, mejor_q, rotacion_sug

    @classmethod
    def evaluar_fase(cls, fase: MedicionFase, angulo_base_v: float = 0.0) -> EvaluacionRotacionFase:
        v = fase.tension.voltios if fase.tension else None
        i = fase.corriente.amperios if fase.corriente else None
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
                tension_v=v,
                corriente_a=i,
                angulo_fasorial_grados=round(angulo_base_v, 1),
                tc_invertido_180=False,
                estado_ti="DESCONECTADO" if (i is None or i <= 0.05) else "CORRECTO",
            )

        s = math.sqrt(p**2 + q**2)
        fp_orig = round(p / s, 3) if s > 0 else 0.0
        phi_orig_rad = math.atan2(q, p)
        phi_orig_deg = round(math.degrees(phi_orig_rad), 1)

        evaluadas, mejor_fp, mejor_p, mejor_q, rotacion_sug = cls._evaluar_rotaciones_optimas(
            p, q, s, fp_orig, phi_orig_rad, phi_orig_deg
        )
        es_invertido = (p < 0) or (rotacion_sug in ("180°", "-180°", "+180°"))

        angulo_i = (angulo_base_v - phi_orig_deg) % 360
        if angulo_i > 180:
            angulo_i -= 360

        estado = "DESCONECTADO" if (i is not None and i <= 0.05) else ("INVERTIDO" if es_invertido else "CORRECTO")

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
            tension_v=v,
            corriente_a=i,
            angulo_fasorial_grados=round(angulo_i, 1),
            tc_invertido_180=es_invertido,
            estado_ti=estado,
        )

    @staticmethod
    def _procesar_alertas_fasoriales(
        alertas_mf: list,
        alertas_desc: list,
        diag_r: EvaluacionRotacionFase,
        diag_s: EvaluacionRotacionFase,
        diag_t: EvaluacionRotacionFase,
    ) -> tuple[list[str], str, str, str, list[str]]:
        alertas_fasoriales: list[str] = []
        estado_r, estado_s, estado_t = diag_r.estado_ti, diag_s.estado_ti, diag_t.estado_ti

        for a in alertas_mf:
            alertas_fasoriales.append(f"[CRÍTICO] TIs en misma fase: {a.mensaje}")
            if a.fase and "R" in a.fase and "S" in a.fase:
                if (diag_r.fp_original or 0.0) < (diag_s.fp_original or 0.0):
                    estado_r = "DUPLICADO (en Fase S)"
                else:
                    estado_s = "DUPLICADO (en Fase R)"

        for a in alertas_desc:
            alertas_fasoriales.append(f"[CRÍTICO] TI Desconectado: {a.mensaje}")
            if a.fase == "R":
                estado_r = "DESCONECTADO"
            elif a.fase == "S":
                estado_s = "DESCONECTADO"
            elif a.fase == "T":
                estado_t = "DESCONECTADO"

        anomalias = []
        if (diag_s.fp_original or 0) < 0.80 and diag_s.rotacion_optima_sugerida == "-60°" and not alertas_mf:
            anomalias.append("Fase S con desfasaje cruzado de -60° (I_S midiendo contra tensión no colineal)")
        if (
            (diag_t.fp_original or 0) < 0.50
            and diag_t.rotacion_optima_sugerida in ("+60°", "-120°")
            and not alertas_desc
        ):
            anomalias.append("Fase T con desfasaje fasorial de +60° / -120° (cruce de tensión V_T/V_S)")

        for anom in anomalias:
            alertas_fasoriales.append(f"[ADVERTENCIA] {anom}")

        return alertas_fasoriales, estado_r, estado_s, estado_t, anomalias

    @classmethod
    def diagnosticar_lectura(
        cls,
        dispositivo_id: str,
        lectura: LecturaInstantanea,
        fases_con_ti: list[str] | set[str] | None = None,
    ) -> DiagnosticoFasorialRed:
        diag_r = cls.evaluar_fase(lectura.fase_r, angulo_base_v=0.0)
        diag_s = cls.evaluar_fase(lectura.fase_s, angulo_base_v=-120.0)
        diag_t = cls.evaluar_fase(lectura.fase_t, angulo_base_v=120.0)

        from src.domain.telemetria.servicios.evaluador_anomalias_fases import EvaluadorAnomaliasFasesService
        from src.domain.telemetria.servicios.evaluador_tis_misma_fase import EvaluadorTisMismaFaseService

        alertas_mf = EvaluadorTisMismaFaseService.evaluar_alerta_tis_en_misma_fase(
            dispositivo_id=dispositivo_id,
            lectura=lectura,
            fases_con_ti=fases_con_ti,
        )
        alertas_desc = EvaluadorAnomaliasFasesService.evaluar_alerta_ti_desconectado(
            dispositivo_id=dispositivo_id,
            lectura=lectura,
            fases_con_ti=fases_con_ti,
        )

        alertas_fasoriales, estado_r, estado_s, estado_t, anomalias = cls._procesar_alertas_fasoriales(
            alertas_mf, alertas_desc, diag_r, diag_s, diag_t
        )

        diag_r = replace(diag_r, estado_ti=estado_r)
        diag_s = replace(diag_s, estado_ti=estado_s)
        diag_t = replace(diag_t, estado_ti=estado_t)

        if alertas_mf or alertas_desc:
            gen = "Anomalía crítica en cableado de Transformadores de Corriente (TIs): " + "; ".join(alertas_fasoriales)
            rec = "Revisar tablero eléctrico: verificar TIs en misma fase y conexiones de secundarios abiertos."
        elif anomalias:
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
            secuencia_fases="DIRECTA",
            rotacion_correcta=len(alertas_mf) == 0 and len(anomalias) == 0,
            alertas_fasoriales=tuple(alertas_fasoriales),
        )

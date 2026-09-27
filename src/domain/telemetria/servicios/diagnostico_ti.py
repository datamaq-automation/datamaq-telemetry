"""Servicio de dominio para diagnóstico de orden de fases e inversión de TI."""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.domain.telemetria.value_objects import CandidatoTI, MedicionFase


@dataclass
class DiagnosticoTIService:
    """Servicio de dominio: diagnóstico de configuración de Transformadores de Intensidad.

    Rankea candidatos de orden de fases e inversión usando coherencia fasorial.
    Métodos puros (sin estado, sin dependencia de infraestructura).
    """

    @staticmethod
    def calcular_s_teorica(p: float, q: float) -> float:
        """Potencia aparente teórica: S = √(P² + Q²)."""
        if p is None or q is None:
            return 0.0
        return math.sqrt(p**2 + q**2)

    @staticmethod
    def calcular_fp_teorico(p: float, s: float) -> float:
        """Factor de potencia teórico: FP = P/S."""
        if s == 0 or p is None:
            return 0.0
        return min(1.0, abs(p) / s)

    @staticmethod
    def error_coherencia_s(p: float, q: float, s_medida: float) -> float:
        """Error % entre S medida y S teórica = √(P²+Q²)."""
        s_teorica = DiagnosticoTIService.calcular_s_teorica(p, q)
        if s_teorica == 0:
            return 0.0
        return 100.0 * abs(s_medida - s_teorica) / s_teorica

    @staticmethod
    def error_coherencia_fp(p: float, s: float, fp_medida: float) -> float:
        """Error % entre FP medida y FP teórico = P/S."""
        fp_teorico = DiagnosticoTIService.calcular_fp_teorico(p, s)
        if fp_medida == 0 and fp_teorico == 0:
            return 0.0
        if fp_teorico == 0:
            return 100.0
        return 100.0 * abs(fp_medida - fp_teorico)

    @staticmethod
    def aplicar_transformacion_ti(
        med_r: MedicionFase,
        med_s: MedicionFase,
        med_t: MedicionFase,
        orden: tuple[str, ...],
        invertido: bool,
    ) -> dict[str, MedicionFase]:
        """Aplica transformación de orden/polaridad a mediciones de fase.

        Args:
            orden: Tupla con reorden de fases (ej. ("S", "R", "T"))
            invertido: Si True, invierte el signo de Q

        Returns:
            Dict {fase_nueva: MedicionFase} después de aplicar transformación
        """
        mediciones_map = {
            "R": med_r,
            "S": med_s,
            "T": med_t,
        }

        resultado: dict[str, MedicionFase] = {}
        for i, fase_original in enumerate(orden):
            med_orig = mediciones_map[fase_original]
            p = med_orig.p
            q = med_orig.q
            s = med_orig.s
            fp = med_orig.fp

            if invertido and q is not None:
                q = -q

            fase_nueva = chr(ord("R") + i)
            resultado[fase_nueva] = MedicionFase(p=p, q=q, s=s, fp=fp)

        return resultado

    @staticmethod
    def rankear_candidatos(
        registros: list[dict],
        fases_con_ti: tuple[str, ...],
    ) -> list[CandidatoTI]:
        """Rankea candidatos según coherencia fasorial promedio.

        Args:
            registros: Lista de dicts con claves p_r, q_r, s_r, fp_r, p_s, ...
            fases_con_ti: Tupla de fases disponibles (ej. ("R", "S"))

        Returns:
            Lista de CandidatoTI ordenados por score descendente
        """
        candidatos: list[CandidatoTI] = []

        ordenes = [
            ("R", "S", "T"),
            ("S", "R", "T"),
            ("R", "T", "S"),
        ]

        # Filtrar órdenes para bifásico
        if len(fases_con_ti) == 2:
            ordenes = [o for o in ordenes if o[0] in fases_con_ti and o[1] in fases_con_ti]

        for orden in ordenes:
            for invertido in [False, True]:
                errs_s = []
                errs_fp = []
                q_signs = []

                for reg in registros:
                    med_r = MedicionFase(
                        p=reg.get("p_r"),
                        q=reg.get("q_r"),
                        s=reg.get("s_r"),
                        fp=reg.get("fp_r"),
                    )
                    med_s = MedicionFase(
                        p=reg.get("p_s"),
                        q=reg.get("q_s"),
                        s=reg.get("s_s"),
                        fp=reg.get("fp_s"),
                    )
                    med_t = MedicionFase(
                        p=reg.get("p_t"),
                        q=reg.get("q_t"),
                        s=reg.get("s_t"),
                        fp=reg.get("fp_t"),
                    )

                    transformadas = DiagnosticoTIService.aplicar_transformacion_ti(
                        med_r, med_s, med_t, orden, invertido
                    )

                    for med in transformadas.values():
                        if med.p is not None and med.q is not None and med.s is not None:
                            err = DiagnosticoTIService.error_coherencia_s(med.p, med.q, med.s)
                            if not math.isnan(err):
                                errs_s.append(err)

                        if med.p is not None and med.s is not None and med.fp is not None:
                            err = DiagnosticoTIService.error_coherencia_fp(med.p, med.s, med.fp)
                            if not math.isnan(err):
                                errs_fp.append(err)

                        if med.q is not None:
                            q_signs.append(1 if med.q > 0 else -1 if med.q < 0 else 0)

                if errs_s or errs_fp:
                    err_s_prom = sum(errs_s) / len(errs_s) if errs_s else 0.0
                    err_fp_prom = sum(errs_fp) / len(errs_fp) if errs_fp else 0.0
                    score = max(0.0, 100.0 - (err_s_prom + err_fp_prom) / 2.0) / 100.0

                    q_sign_mode = max(q_signs, key=q_signs.count) if q_signs else 0
                    q_coherencia_str = (
                        "Q positiva (inductivo)"
                        if q_sign_mode > 0
                        else "Q negativa (capacitivo)"
                        if q_sign_mode < 0
                        else "Q ≈ 0"
                    )

                    justificacion = f"Error S: {err_s_prom:.1f}%, Error FP: {err_fp_prom:.1f}%, {q_coherencia_str}"
                    candidatos.append(CandidatoTI(orden, invertido, score, justificacion))

        return sorted(candidatos, key=lambda c: c.score, reverse=True)

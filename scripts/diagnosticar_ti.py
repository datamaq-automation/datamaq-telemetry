#!/usr/bin/env python3
"""Diagnóstico de orden de fases e inversión de TI analizando histórico de datos.

Rankea 6 candidatos de configuración (3 órdenes × 2 polaridades) por coherencia fasorial.

Uso:
  # Análisis de 24 horas: Trafo 2
  venv/bin/python scripts/diagnosticar_ti.py \\
    --device-id c91713f1-0621-4a33-9279-c5327a317d96 \\
    --periodo-horas 24 \\
    --metrica coherencia

  # Análisis de 7 días
  venv/bin/python scripts/diagnosticar_ti.py \\
    --device-id c91713f1-0621-4a33-9279-c5327a317d96 \\
    --periodo-horas 168 \\
    --metrica coherencia \\
    --verbose
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import desc, select

from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.models import TelemetryInstantaneousModel
from src.infrastructure.sqlalchemy.repositories.dispositivos_repository import MySQLDispositivosRepository


@dataclass
class CandidatoTI:
    orden_fases: list[str]
    invertido: bool
    score: float
    justificacion: str

    @property
    def posicion(self) -> str:
        return f"{','.join(self.orden_fases)}{' (INV)' if self.invertido else ''}"


@dataclass
class MedicionFase:
    p: float | None
    q: float | None
    s: float | None
    fp: float | None


def calcular_s_teorica(p: float, q: float) -> float:
    """Calcula potencia aparente teórica: S = √(P² + Q²)."""
    if p is None or q is None:
        return 0.0
    return math.sqrt(p**2 + q**2)


def calcular_fp_teorico(p: float, s: float) -> float:
    """Calcula FP teórico: FP = P/S."""
    if s == 0 or p is None:
        return 0.0
    return min(1.0, abs(p) / s)


def error_coherencia_s(p: float, q: float, s_medida: float) -> float:
    """Error % entre S medida y S teórica = √(P²+Q²)."""
    s_teorica = calcular_s_teorica(p, q)
    if s_teorica == 0:
        return 0.0
    return 100.0 * abs(s_medida - s_teorica) / s_teorica


def error_coherencia_fp(p: float, s: float, fp_medida: float) -> float:
    """Error % entre FP medida y FP teórico = P/S."""
    fp_teorico = calcular_fp_teorico(p, s)
    if fp_medida == 0 and fp_teorico == 0:
        return 0.0
    if fp_teorico == 0:
        return 100.0
    return 100.0 * abs(fp_medida - fp_teorico)


def aplicar_transformacion_ti(
    mediciones_r: MedicionFase,
    mediciones_s: MedicionFase,
    mediciones_t: MedicionFase,
    orden: list[str],
    invertido: bool,
) -> dict[str, MedicionFase]:
    """Aplica transformación de orden/polaridad a potencias.

    Returns: {fase_nueva: MedicionFase} después de aplicar transformación
    """
    mediciones_map = {
        "R": mediciones_r,
        "S": mediciones_s,
        "T": mediciones_t,
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


def rankear_candidatos(
    registros: list[dict],
    fases_con_ti: list[str],
) -> list[CandidatoTI]:
    """Rankea candidatos según coherencia fasorial promedio."""
    candidatos: list[CandidatoTI] = []

    ordenes = [
        ["R", "S", "T"],
        ["S", "R", "T"],
        ["R", "T", "S"],
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
                med_r = MedicionFase(p=reg.get("p_r"), q=reg.get("q_r"), s=reg.get("s_r"), fp=reg.get("fp_r"))
                med_s = MedicionFase(p=reg.get("p_s"), q=reg.get("q_s"), s=reg.get("s_s"), fp=reg.get("fp_s"))
                med_t = MedicionFase(p=reg.get("p_t"), q=reg.get("q_t"), s=reg.get("s_t"), fp=reg.get("fp_t"))

                transformadas = aplicar_transformacion_ti(med_r, med_s, med_t, orden, invertido)

                for fase, med in transformadas.items():
                    if med.p is not None and med.q is not None and med.s is not None:
                        err = error_coherencia_s(med.p, med.q, med.s)
                        if not math.isnan(err):
                            errs_s.append(err)

                    if med.p is not None and med.s is not None and med.fp is not None:
                        err = error_coherencia_fp(med.p, med.s, med.fp)
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


def imprimir_tabla_candidatos(candidatos: list[CandidatoTI]) -> None:
    """Imprime tabla de candidatos rankeados."""
    print("\n" + "=" * 100)
    print(" CANDIDATOS RANKEADOS POR COHERENCIA FASORIAL")
    print("=" * 100)
    print(f"{'Pos':<4} | {'Orden Fases':<15} | {'Invertido':<10} | {'Score':<7} | Justificación")
    print("-" * 100)

    for i, c in enumerate(candidatos[:6], 1):
        invertido_str = "SÍ" if c.invertido else "NO"
        print(f"{i:<4} | {','.join(c.orden_fases):<15} | {invertido_str:<10} | {c.score:.4f}  | {c.justificacion}")

    print("=" * 100)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnóstico de orden de fases e inversión de TI por análisis histórico"
    )
    parser.add_argument("--device-id", type=str, required=True, help="UUID del dispositivo")
    parser.add_argument("--periodo-horas", type=int, default=24, help="Período histórico a analizar (horas)")
    parser.add_argument("--metrica", type=str, default="coherencia", choices=["coherencia"], help="Métrica de ranking")
    parser.add_argument("--verbose", action="store_true", help="Imprimir detalles")

    args = parser.parse_args()

    try:
        session_factory = get_session_factory()
        with session_factory() as session:
            repo_disp = MySQLDispositivosRepository(session)
            dispositivo = repo_disp.obtener_por_id(args.device_id)

            if not dispositivo:
                print(f"Error: Dispositivo {args.device_id} no encontrado.")
                return 1

            fases_con_ti = [f.strip().upper() for f in dispositivo.fases_con_ti.split(",")]

            inicio = datetime.now(timezone.utc) - timedelta(hours=args.periodo_horas)
            stmt = (
                select(TelemetryInstantaneousModel)
                .where(TelemetryInstantaneousModel.device_id == args.device_id)
                .where(TelemetryInstantaneousModel.recorded_at >= inicio)
                .order_by(desc(TelemetryInstantaneousModel.recorded_at))
            )
            registros_db = session.execute(stmt).scalars().all()

            if not registros_db:
                print(f"No se encontraron registros en los últimos {args.periodo_horas} horas.")
                return 1

            datos = []
            for reg in registros_db:
                datos.append(
                    {
                        "registrado_en": reg.recorded_at,
                        "p_r": float(reg.active_power_r) if reg.active_power_r is not None else None,
                        "p_s": float(reg.active_power_s) if reg.active_power_s is not None else None,
                        "p_t": float(reg.active_power_t) if reg.active_power_t is not None else None,
                        "q_r": float(reg.reactive_power_r) if reg.reactive_power_r is not None else None,
                        "q_s": float(reg.reactive_power_s) if reg.reactive_power_s is not None else None,
                        "q_t": float(reg.reactive_power_t) if reg.reactive_power_t is not None else None,
                        "s_r": float(reg.apparent_power_r) if reg.apparent_power_r is not None else None,
                        "s_s": float(reg.apparent_power_s) if reg.apparent_power_s is not None else None,
                        "s_t": float(reg.apparent_power_t) if reg.apparent_power_t is not None else None,
                        "fp_r": float(reg.power_factor_r) if reg.power_factor_r is not None else None,
                        "fp_s": float(reg.power_factor_s) if reg.power_factor_s is not None else None,
                        "fp_t": float(reg.power_factor_t) if reg.power_factor_t is not None else None,
                    }
                )

            ubicacion = dispositivo.ubicacion_tag or "desconocido"
            inicio_str = inicio.strftime("%Y-%m-%d %H:%M")
            fin_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

            print(f"\nDiagnóstico de TI para {ubicacion} ({dispositivo.device_uid})")
            print(f"Período: {inicio_str} a {fin_str} ({args.periodo_horas}h)")
            print(f"Registros analizados: {len(datos)}")
            print(f"Fases con TI: {','.join(fases_con_ti)}")

            candidatos = rankear_candidatos(datos, fases_con_ti)
            imprimir_tabla_candidatos(candidatos)

            if candidatos:
                top = candidatos[0]
                config_actual_str = f"Config actual: {','.join(fases_con_ti)}, invertido={'false' if not dispositivo.invertido else 'true'}"
                print(f"\n{config_actual_str}")
                print(f"Recomendación: {top.posicion} (Score: {top.score:.4f})")
                if top.score > 0.98:
                    print("✓ Candidato 1 es el ACTUAL y tiene coherencia máxima → ESTÁ CORRECTAMENTE CONFIGURADO")
                elif top.score > 0.70:
                    print("⚠ Score > 0.70 → Configuración probablemente CORRECTA, valida con patrón certificado")
                else:
                    print("✗ Score bajo → Necesita diagnóstico con patrón certificado en campo")

            return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

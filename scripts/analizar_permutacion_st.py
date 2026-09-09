#!/usr/bin/env python3
"""Script de ingeniería electrotécnica para simular y analizar la alternancia de fases S y T.

Evalúa metrológicamente el intercambio de fases (bornes de tensión V_S <-> V_T y/o
transformadores de corriente I_S <-> I_T), tanto en régimen bifásico (pre-sábado con R inactiva)
como en régimen trifásico (post-lunes con R activa y T con polaridad directa corregida).
Reutiliza entidades y servicios de src/domain/telemetria.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path

# Ajustar PYTHONPATH para importar desde src/
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.domain.telemetria.entities import MedicionFase  # noqa: E402
from src.domain.telemetria.services import AnalizadorFasorialService  # noqa: E402
from src.domain.telemetria.value_objects import (  # noqa: E402
    Corriente,
    FactorPotencia,
    PotenciaActiva,
    PotenciaReactiva,
    Tension,
)


@dataclass(frozen=True)
class EstadoFasorialFase:
    fase: str
    v_rms: float
    i_rms: float
    p_w: float
    q_var: float
    s_va: float
    fp: float
    phi_deg: float
    naturaleza: str


def clasificar_naturaleza(p_w: float, q_var: float, s_va: float) -> str:
    if s_va < 100 or abs(p_w) < 50:
        return "Inactiva / Sin Carga"
    if p_w < 0:
        return f"Inverso / Inyección (P<0, Q={'Ind' if q_var > 0 else 'Cap'})"
    if abs(q_var) < 0.10 * s_va:
        return "Casi Resistivo (FP > 0.995)"
    if q_var < 0:
        return "Capacitivo (Q < 0, Corriente en Adelanto)"
    return "Inductivo / Reactivo (Q > 0, Corriente en Atraso)"


def crear_medicion(v: float, i: float, p: float, q: float) -> MedicionFase:
    s = math.sqrt(p**2 + q**2)
    fp_val = round(p / s, 3) if s > 0 else 1.0
    return MedicionFase(
        tension=Tension(v),
        corriente=Corriente(i),
        potencia_activa=PotenciaActiva(p),
        potencia_reactiva=PotenciaReactiva(q),
        factor_potencia=FactorPotencia(fp_val),
    )


def extraer_estado_fase(fase_nombre: str, v: float, i: float, p: float, q: float) -> EstadoFasorialFase:
    s = math.sqrt(p**2 + q**2)
    fp = round(p / s, 3) if s > 0 else 0.0
    phi_rad = math.atan2(q, p)
    phi_deg = round(math.degrees(phi_rad), 1)
    nat = clasificar_naturaleza(p, q, s)
    return EstadoFasorialFase(
        fase=fase_nombre,
        v_rms=round(v, 1),
        i_rms=round(i, 1),
        p_w=round(p, 1),
        q_var=round(q, 1),
        s_va=round(s, 1),
        fp=fp,
        phi_deg=phi_deg,
        naturaleza=nat,
    )


def simular_intercambios_st(
    v_s: float,
    i_s: float,
    p_s: float,
    q_s: float,
    v_t: float,
    i_t: float,
    p_t: float,
    q_t: float,
    secuencia_directa: bool = True,
) -> dict[str, dict[str, EstadoFasorialFase]]:
    delta_v_ts = -120.0 if secuencia_directa else +120.0

    phi_s_rad = math.atan2(q_s, p_s)
    phi_t_rad = math.atan2(q_t, p_t)

    s_s = math.sqrt(p_s**2 + q_s**2)
    s_t = math.sqrt(p_t**2 + q_t**2)

    escenarios: dict[str, dict[str, EstadoFasorialFase]] = {}

    # 1. Estado Actual (Sin intervención)
    escenarios["0_Actual_Sin_Cambios"] = {
        "S": extraer_estado_fase("S", v_s, i_s, p_s, q_s),
        "T": extraer_estado_fase("T", v_t, i_t, p_t, q_t),
    }

    # 2. Intercambio de Bornes de Tensión (V_S <-> V_T en bornera de tensión)
    phi_s_swap_v = phi_s_rad + math.radians(delta_v_ts)
    p_s_swap_v = s_s * math.cos(phi_s_swap_v)
    q_s_swap_v = s_s * math.sin(phi_s_swap_v)

    phi_t_swap_v = phi_t_rad - math.radians(delta_v_ts)
    p_t_swap_v = s_t * math.cos(phi_t_swap_v)
    q_t_swap_v = s_t * math.sin(phi_t_swap_v)

    escenarios["1_Swap_Tensiones_VS_VT"] = {
        "S": extraer_estado_fase("S", v_t, i_s, p_s_swap_v, q_s_swap_v),
        "T": extraer_estado_fase("T", v_s, i_t, p_t_swap_v, q_t_swap_v),
    }

    # 3. Intercambio de Secundarios de Corriente (I_S <-> I_T en bornera de TIs)
    phi_s_swap_i = phi_t_rad - math.radians(delta_v_ts)
    p_s_swap_i = s_t * math.cos(phi_s_swap_i)
    q_s_swap_i = s_t * math.sin(phi_s_swap_i)

    phi_t_swap_i = phi_s_rad + math.radians(delta_v_ts)
    p_t_swap_i = s_s * math.cos(phi_t_swap_i)
    q_t_swap_i = s_s * math.sin(phi_t_swap_i)

    escenarios["2_Swap_Corrientes_IS_IT"] = {
        "S": extraer_estado_fase("S", v_s, i_t, p_s_swap_i, q_s_swap_i),
        "T": extraer_estado_fase("T", v_t, i_s, p_t_swap_i, q_t_swap_i),
    }

    # 4. Swap I_S <-> I_T con Inversión de Sentido en T (+180°)
    phi_s_swap_inv = phi_s_swap_i + math.pi
    p_s_swap_inv = s_t * math.cos(phi_s_swap_inv)
    q_s_swap_inv = s_t * math.sin(phi_s_swap_inv)

    phi_t_swap_inv = phi_t_swap_i + math.pi
    p_t_swap_inv = s_s * math.cos(phi_t_swap_inv)
    q_t_swap_inv = s_s * math.sin(phi_t_swap_inv)

    escenarios["3_Swap_Corrientes_IS_IT_con_Inversion_180"] = {
        "S": extraer_estado_fase("S", v_s, i_t, p_s_swap_inv, q_s_swap_inv),
        "T": extraer_estado_fase("T", v_t, i_s, p_t_swap_inv, q_t_swap_inv),
    }

    # 5. Compensación Metrológica Óptima de Fase (S: -60°, T: +60°)
    med_s = crear_medicion(v_s, i_s, p_s, q_s)
    med_t = crear_medicion(v_t, i_t, p_t, q_t)
    eval_s = AnalizadorFasorialService.evaluar_fase(med_s)
    eval_t = AnalizadorFasorialService.evaluar_fase(med_t)

    escenarios["4_Rotacion_Optima_Metrologica_S-60_T+60"] = {
        "S": extraer_estado_fase(
            "S",
            v_s,
            i_s,
            eval_s.p_con_rotacion_optima_w or p_s,
            eval_s.q_con_rotacion_optima_var or q_s,
        ),
        "T": extraer_estado_fase(
            "T",
            v_t,
            i_t,
            eval_t.p_con_rotacion_optima_w or p_t,
            eval_t.q_con_rotacion_optima_var or q_t,
        ),
    }

    return escenarios


def procesar_muestras_csv(
    ruta_csv: Path,
    filtro_pre: str,
    filtro_post: str,
) -> None:
    if not ruta_csv.exists():
        print(f"Error: no se encontró el archivo CSV en '{ruta_csv}'")
        sys.exit(1)

    with open(ruta_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        filas = list(reader)

    print(f"Total registros cargados del reporte: {len(filas)}")

    filas_pre = [r for r in filas if filtro_pre in r["timestamp_LOCAL"]]
    filas_post = [r for r in filas if filtro_post in r["timestamp_LOCAL"]]

    if not filas_pre:
        filas_pre = [r for r in filas if float(r.get("Corriente Por Fase (I_R) [A]", 0)) < 3.0]
    if not filas_post:
        filas_post = filas[-10:]

    muestra_pre = filas_pre[0]
    muestra_post = filas_post[-1]

    bloques = [
        (
            "PERIODO 1: RÉGIMEN BIFÁSICO (PREVIO AL SÁBADO 05/09 - FASE R INACTIVA)",
            muestra_pre,
            False,
        ),
        (
            "PERIODO 2: RÉGIMEN TRIFÁSICO (POST-LUNES 07/09 16:35 - T CON POLARIDAD CORREGIDA)",
            muestra_post,
            True,
        ),
    ]

    for titulo, row, r_activa in bloques:
        print("\n" + "=" * 95)
        print(f"  {titulo}")
        print(f"  Muestra temporal: {row['timestamp_LOCAL']}")
        print("=" * 95)

        vr = float(row["Tension Por Fase (V_R) [V]"])
        ir = float(row["Corriente Por Fase (I_R) [A]"])
        pr = float(row["Potencia Activa Por Fase (P_R) [W]"])
        qr = float(row["Potencia Reactiva Por Fase (Q_R) [VAr]"])
        estado_r = extraer_estado_fase("R", vr, ir, pr, qr)

        print(
            f"  [Referencia Fase R] V={estado_r.v_rms:.1f}V | I={estado_r.i_rms:.1f}A | "
            f"P={estado_r.p_w:+.0f}W | Q={estado_r.q_var:+.0f}VAr | FP={estado_r.fp:.3f} | "
            f"Phi={estado_r.phi_deg:+.1f}° -> {estado_r.naturaleza}"
        )
        print("-" * 95)

        vs = float(row["Tension Por Fase (V_S) [V]"])
        is_ = float(row["Corriente Por Fase (I_S) [A]"])
        ps = float(row["Potencia Activa Por Fase (P_S) [W]"])
        qs = float(row["Potencia Reactiva Por Fase (Q_S) [VAr]"])

        vt = float(row["Tension Por Fase (V_T) [V]"])
        it = float(row["Corriente Por Fase (I_T) [A]"])
        pt = float(row["Potencia Activa Por Fase (P_T) [W]"])
        qt = float(row["Potencia Reactiva Por Fase (Q_T) [VAr]"])

        escenarios = simular_intercambios_st(vs, is_, ps, qs, vt, it, pt, qt)

        for esc_nombre, fases_res in escenarios.items():
            s_fase = fases_res["S"]
            t_fase = fases_res["T"]
            p_tot = (estado_r.p_w if r_activa else 0) + s_fase.p_w + t_fase.p_w
            q_tot = (estado_r.q_var if r_activa else 0) + s_fase.q_var + t_fase.q_var
            s_tot = math.sqrt(p_tot**2 + q_tot**2)
            fp_tot = round(p_tot / s_tot, 3) if s_tot > 0 else 0.0
            nat_tot = "Inductivo (Q>0)" if q_tot > 0 else "Capacitivo (Q<0)"

            print(f"\n>> ESCENARIO: {esc_nombre}")
            print(
                f"   Fase S: P={s_fase.p_w:+8.0f} W | Q={s_fase.q_var:+8.0f} VAr | FP={s_fase.fp:.3f} "
                f"(Phi={s_fase.phi_deg:+6.1f}°) -> {s_fase.naturaleza}"
            )
            print(
                f"   Fase T: P={t_fase.p_w:+8.0f} W | Q={t_fase.q_var:+8.0f} VAr | FP={t_fase.fp:.3f} "
                f"(Phi={t_fase.phi_deg:+6.1f}°) -> {t_fase.naturaleza}"
            )
            print(f"   TOTAL RED: P={p_tot:+8.0f} W | Q={q_tot:+8.0f} VAr | FP={fp_tot:.3f} -> {nat_tot}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analizador electrotécnico de alternancia de fases S y T (pre y post sábado)"
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("/home/agustin/Descargas/Reporte 07-09-2026 18_09_19 (GMT-3).csv"),
        help="Ruta al archivo CSV de telemetría",
    )
    parser.add_argument(
        "--filtro-pre",
        type=str,
        default="04-09-2026 15:",
        help="Subcadena para filtrar muestra previa al sábado (2 fases)",
    )
    parser.add_argument(
        "--filtro-post",
        type=str,
        default="07-09-2026 17:",
        help="Subcadena para filtrar muestra posterior al lunes 16:35 (3 fases)",
    )
    args = parser.parse_args()

    procesar_muestras_csv(args.csv, args.filtro_pre, args.filtro_post)

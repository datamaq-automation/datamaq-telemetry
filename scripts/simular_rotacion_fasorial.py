#!/usr/bin/env python3
"""Script de diagnóstico metrológico para simulación de rotación y permutación fasorial.

Analiza lecturas eléctricas trifásicas para detectar transposiciones físicas entre
canales de tensión (V) y corriente (I), evaluando la convergencia del Factor de Potencia.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path


def calcular_fasor_fase(p: float, q: float) -> tuple[float, float]:
    s = math.sqrt(p**2 + q**2)
    fp = p / s if s > 0 else 0.0
    phi_rad = math.atan2(q, p)
    return fp, math.degrees(phi_rad)


def rotar_fasor(p: float, q: float, shift_deg: float) -> tuple[float, float, float]:
    s = math.sqrt(p**2 + q**2)
    phi = math.atan2(q, p) + math.radians(shift_deg)
    p_rot = s * math.cos(phi)
    q_rot = s * math.sin(phi)
    fp_rot = p_rot / s if s > 0 else 0.0
    return fp_rot, p_rot, q_rot


def analizar_archivo_csv(ruta_csv: Path, filtro_fecha: str | None = None) -> None:
    if not ruta_csv.exists():
        print(f"Error: el archivo {ruta_csv} no existe.", file=sys.stderr)
        sys.exit(1)

    with open(ruta_csv, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if filtro_fecha:
        rows = [r for r in rows if filtro_fecha in r.get("timestamp_LOCAL", "")]

    if not rows:
        print("No se encontraron registros con el filtro indicado.", file=sys.stderr)
        return

    print(f"=== ANÁLISIS DE ROTACIÓN FASORIAL METROLÓGICA ({len(rows)} muestras) ===")
    angulos_prueba = [-120, -60, +60, +120, 180]

    for fase, col_p, col_q in [
        ("Fase R", "Potencia Activa Por Fase (P_R) [W]", "Potencia Reactiva Por Fase (Q_R) [VAr]"),
        ("Fase S", "Potencia Activa Por Fase (P_S) [W]", "Potencia Reactiva Por Fase (Q_S) [VAr]"),
        ("Fase T", "Potencia Activa Por Fase (P_T) [W]", "Potencia Reactiva Por Fase (Q_T) [VAr]"),
    ]:
        p_vals = [float(r[col_p]) for r in rows if r.get(col_p)]
        q_vals = [float(r[col_q]) for r in rows if r.get(col_q)]
        if not p_vals or not q_vals:
            continue

        p_prom = sum(p_vals) / len(p_vals)
        q_prom = sum(q_vals) / len(q_vals)
        fp_orig, phi_orig = calcular_fasor_fase(p_prom, q_prom)

        print(
            f"\n[{fase}] Promedio Original: FP={fp_orig:+.3f} | Phi={phi_orig:+.1f}° | P={p_prom:+.0f}W | Q={q_prom:+.0f}VAr"
        )
        for shift in angulos_prueba:
            fp_rot, p_rot, q_rot = rotar_fasor(p_prom, q_prom, shift)
            marcador = " <<< ÓPTIMO (>0.85)" if fp_rot >= 0.85 else ""
            print(f"  Rotación {shift:+4d}°: FP={fp_rot:+.3f} | P={p_rot:+8.0f}W | Q={q_rot:+8.0f}VAr{marcador}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulador de rotación fasorial")
    parser.add_argument("csv_path", type=Path, help="Ruta al reporte CSV")
    parser.add_argument("--filtro", type=str, default="07-09-2026 16:", help="Filtro de timestamp_LOCAL")
    args = parser.parse_args()
    analizar_archivo_csv(args.csv_path, args.filtro)

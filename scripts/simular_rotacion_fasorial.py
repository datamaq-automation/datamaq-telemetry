#!/usr/bin/env python3
"""Script delgado de diagnóstico metrológico para simulación de rotación fasorial.

Delega 100% de la lógica fasorial a src.domain.telemetria.services.AnalizadorFasorialService.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Garantizar PYTHONPATH para importar desde src/
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.domain.telemetria.entities import MedicionFase  # noqa: E402
from src.domain.telemetria.services import AnalizadorFasorialService  # noqa: E402
from src.domain.telemetria.value_objects import PotenciaActiva, PotenciaReactiva  # noqa: E402


def analizar_archivo_csv(ruta_csv: Path, filtro_fecha: str | None = None) -> None:
    if not ruta_csv.exists():
        print(f"Error: el archivo {ruta_csv} no existe.", file=sys.stderr)
        sys.exit(1)

    with open(ruta_csv, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if not filtro_fecha or filtro_fecha in r.get("timestamp_LOCAL", "")]

    if not rows:
        print("No se encontraron registros con el filtro indicado.", file=sys.stderr)
        return

    print(f"=== ANÁLISIS DE ROTACIÓN FASORIAL METROLÓGICA ({len(rows)} muestras) ===")

    for fase_nombre, col_p, col_q in [
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

        fase = MedicionFase(
            potencia_activa=PotenciaActiva(p_prom),
            potencia_reactiva=PotenciaReactiva(q_prom),
        )
        res = AnalizadorFasorialService.evaluar_fase(fase)

        print(
            f"\n[{fase_nombre}] Promedio Original: FP={res.fp_original:+.3f} | Phi={res.phi_deg_original:+.1f}° | P={res.potencia_activa_w:+.0f}W | Q={res.potencia_reactiva_var:+.0f}VAr"
        )
        for angulo, m in res.rotaciones_evaluadas.items():
            if angulo == "0°":
                continue
            marcador = " <<< ÓPTIMO (>0.85)" if m["fp"] >= 0.85 and m["p_w"] > 0 else ""
            print(
                f"  Rotación {angulo:>5s}: FP={m['fp']:+.3f} | P={m['p_w']:+8.0f}W | Q={m['q_var']:+8.0f}VAr{marcador}"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulador de rotación fasorial")
    parser.add_argument("csv_path", type=Path, help="Ruta al reporte CSV")
    parser.add_argument("--filtro", type=str, default="07-09-2026 16:", help="Filtro de timestamp_LOCAL")
    args = parser.parse_args()
    analizar_archivo_csv(args.csv_path, args.filtro)

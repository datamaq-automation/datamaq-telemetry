#!/usr/bin/env python3
"""Compara dos medidores (ej., Trafo 1 vs. Trafo 2) para validar coherencia de configs.

Uso:
  venv/bin/python scripts/comparar_ti_bifasico.py \\
    --device-a 7434647d-5b87-4d4e-b4a5-a0d351315f0a \\
    --device-b c91713f1-0621-4a33-9279-c5327a317d96 \\
    --fecha-inicio 2026-09-17 \\
    --fecha-fin 2026-09-27
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import select

from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.models import TelemetryInstantaneousModel
from src.infrastructure.sqlalchemy.repositories.dispositivos_repository import MySQLDispositivosRepository


def calcular_promedio_metrica(
    registros: Sequence,
    columna_activa: str,
    columna_reactiva: str,
) -> tuple[float, float, str]:
    """Calcula promedios de P, Q y deduce tipo de carga."""
    if not registros:
        return 0.0, 0.0, "N/A"

    p_total = sum(getattr(r, columna_activa) or 0.0 for r in registros) / len(registros)
    q_total = sum(getattr(r, columna_reactiva) or 0.0 for r in registros) / len(registros)

    if q_total > 100.0:
        tipo = "Inductivo"
    elif q_total < -100.0:
        tipo = "Capacitivo"
    else:
        tipo = "Resistivo"

    return p_total, q_total, tipo


def main() -> int:
    parser = argparse.ArgumentParser(description="Comparar configuración de TI entre dos medidores")
    parser.add_argument("--device-a", type=str, required=True, help="UUID del primer dispositivo (referencia)")
    parser.add_argument("--device-b", type=str, required=True, help="UUID del segundo dispositivo")
    parser.add_argument("--fecha-inicio", type=str, default="2026-09-17", help="Fecha inicio (YYYY-MM-DD)")
    parser.add_argument("--fecha-fin", type=str, default="2026-09-27", help="Fecha fin (YYYY-MM-DD)")
    parser.add_argument("--verbose", action="store_true", help="Detalles adicionales")

    args = parser.parse_args()

    try:
        session_factory = get_session_factory()
        with session_factory() as session:
            repo_disp = MySQLDispositivosRepository(session)

            dev_a = repo_disp.obtener_por_id(args.device_a)
            dev_b = repo_disp.obtener_por_id(args.device_b)

            if not dev_a or not dev_b:
                print("Error: Uno o ambos dispositivos no encontrados.")
                return 1

            inicio = datetime.strptime(args.fecha_inicio, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            fin = datetime.strptime(args.fecha_fin, "%Y-%m-%d").replace(tzinfo=timezone.utc)

            stmt_a = (
                select(TelemetryInstantaneousModel)
                .where(TelemetryInstantaneousModel.device_id == args.device_a)
                .where(TelemetryInstantaneousModel.recorded_at >= inicio)
                .where(TelemetryInstantaneousModel.recorded_at <= fin)
            )
            stmt_b = (
                select(TelemetryInstantaneousModel)
                .where(TelemetryInstantaneousModel.device_id == args.device_b)
                .where(TelemetryInstantaneousModel.recorded_at >= inicio)
                .where(TelemetryInstantaneousModel.recorded_at <= fin)
            )

            regs_a = session.execute(stmt_a).scalars().all()
            regs_b = session.execute(stmt_b).scalars().all()

            if not regs_a or not regs_b:
                print("Error: Datos insuficientes en período especificado.")
                return 1

            print("\n" + "=" * 100)
            print(
                f" COMPARATIVA: {dev_a.ubicacion_tag or 'Dispositivo A'} vs. {dev_b.ubicacion_tag or 'Dispositivo B'}"
            )
            print("=" * 100)
            print(f"{'Métrica':<20} | {'Dispositivo A':<25} | {'Dispositivo B':<25} | Coherencia")
            print("-" * 100)

            config_a_str = f"{dev_a.fases_con_ti}, inv={dev_a.invertido}"
            config_b_str = f"{dev_b.fases_con_ti}, inv={dev_b.invertido}"
            coherencia_config = "✓ Opuestas" if config_a_str != config_b_str else "✗ Iguales"
            print(f"{'Config':<20} | {config_a_str:<25} | {config_b_str:<25} | {coherencia_config}")

            p_a, q_a, tipo_a = calcular_promedio_metrica(regs_a, "total_active_power", "total_reactive_power")
            p_b, q_b, tipo_b = calcular_promedio_metrica(regs_b, "total_active_power", "total_reactive_power")

            print(f"{'P promedio (W)':<20} | {p_a:>20.0f} | {p_b:>20.0f} | Ambas > 0")
            print(f"{'Q promedio (VAR)':<20} | {q_a:>20.0f} | {q_b:>20.0f} | Signos opuestos")
            print(f"{'Tipo carga':<20} | {tipo_a:<25} | {tipo_b:<25} | Diferentes")

            print("\n" + "=" * 100)
            print(" INTERPRETACIÓN")
            print("=" * 100)

            if q_a > 0 and q_b < 0:
                print("✓ Q con signos OPUESTOS → Configs de TI probablemente CORRECTAS")
                print("  Hipótesis: Cargas realmente diferentes (A es inductivo, B es capacitivo)")
            elif q_a > 0 and q_b > 0:
                print("⚠ Q con MISMO SIGNO → Posible error en uno de los dos TI")
                print(f"  Verifica: ¿{dev_b.ubicacion_tag or 'B'} es realmente capacitivo?")
                print(f"  Si no, invertir config en {dev_b.ubicacion_tag or 'B'}")
            elif q_a < 0 and q_b < 0:
                print("⚠ Q con MISMO SIGNO → Posible error en uno de los dos TI")
                print(f"  Verifica: ¿{dev_a.ubicacion_tag or 'A'} es realmente capacitivo?")
                print(f"  Si no, invertir config en {dev_a.ubicacion_tag or 'A'}")

            print("=" * 100)
            return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

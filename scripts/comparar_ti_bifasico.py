#!/usr/bin/env python3
"""Compara dos medidores (Trafo 1 vs. Trafo 2) para validar coherencia de configs.

Uso:
  venv/bin/python scripts/comparar_ti_bifasico.py \\
    --device-a 7434647d-5b87-4d4e-b4a5-a0d351315f0a \\
    --device-b c91713f1-0621-4a33-9279-c5327a317d96
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import select

from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.models import TelemetryInstantaneousModel
from src.infrastructure.sqlalchemy.repositories.dispositivos_repository import (
    MySQLDispositivosRepository,
)


def calcular_promedio_q(registros, columna_reactiva: str) -> tuple[float, str]:
    """Calcula promedio de Q y deduce tipo de carga."""
    if not registros:
        return 0.0, "N/A"

    q_values = [float(getattr(r, columna_reactiva) or 0.0) for r in registros]
    q_total = sum(q_values) / len(q_values) if q_values else 0.0

    if q_total > 100.0:
        tipo = "Inductivo"
    elif q_total < -100.0:
        tipo = "Capacitivo"
    else:
        tipo = "Resistivo"

    return q_total, tipo


def main() -> int:
    parser = argparse.ArgumentParser(description="Comparar configuración de TI entre dos medidores")
    parser.add_argument("--device-a", type=str, required=True, help="UUID del medidor A")
    parser.add_argument("--device-b", type=str, required=True, help="UUID del medidor B")
    parser.add_argument("--fecha-inicio", type=str, default="2026-09-17")
    parser.add_argument("--fecha-fin", type=str, default="2026-09-27")

    args = parser.parse_args()

    try:
        session_factory = get_session_factory()
        with session_factory() as session:
            repo_disp = MySQLDispositivosRepository(session)
            dev_a = repo_disp.obtener_por_id(args.device_a)
            dev_b = repo_disp.obtener_por_id(args.device_b)

            if not dev_a or not dev_b:
                print("Error: Uno o ambos dispositivos no encontrados.", file=sys.stderr)
                return 1

            inicio = datetime.strptime(args.fecha_inicio, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            fin = datetime.strptime(args.fecha_fin, "%Y-%m-%d").replace(tzinfo=timezone.utc)

            for device_id, dev in [(args.device_a, dev_a), (args.device_b, dev_b)]:
                stmt = (
                    select(TelemetryInstantaneousModel)
                    .where(TelemetryInstantaneousModel.device_id == device_id)
                    .where(TelemetryInstantaneousModel.recorded_at >= inicio)
                    .where(TelemetryInstantaneousModel.recorded_at <= fin)
                )
                registros = session.execute(stmt).scalars().all()

                q_a, tipo_a = calcular_promedio_q(registros, "total_reactive_power")
                q_b, tipo_b = calcular_promedio_q(
                    registros if device_id == args.device_b else [], "total_reactive_power"
                )

            print("\n" + "=" * 100)
            print(f" COMPARATIVA: {dev_a.ubicacion_tag or 'A'} vs. {dev_b.ubicacion_tag or 'B'}")
            print("=" * 100)

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

            q_a, tipo_a = calcular_promedio_q(regs_a, "total_reactive_power")
            q_b, tipo_b = calcular_promedio_q(regs_b, "total_reactive_power")

            config_a_str = f"{dev_a.fases_con_ti}, inv={dev_a.invertido}"
            config_b_str = f"{dev_b.fases_con_ti}, inv={dev_b.invertido}"
            coherencia = "✓ Opuestas" if config_a_str != config_b_str else "✗ Iguales"

            print(f"{'Métrica':<20} | {'Dispositivo A':<25} | {'Dispositivo B':<25} | Coherencia")
            print("-" * 100)
            print(f"{'Config':<20} | {config_a_str:<25} | {config_b_str:<25} | {coherencia}")
            print(
                f"{'Q promedio (VAR)':<20} | {q_a:>20.0f} | {q_b:>20.0f} | Signos {'opuestos' if (q_a > 0) != (q_b > 0) else 'iguales'}"
            )
            print(f"{'Tipo carga':<20} | {tipo_a:<25} | {tipo_b:<25} | Diferentes")
            print("=" * 100)

            if (q_a > 0) != (q_b > 0):
                print("✓ Q con signos OPUESTOS → Configs probablemente CORRECTAS")
            else:
                print("⚠ Q con MISMO SIGNO → Revisar configuración")

            return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

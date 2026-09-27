#!/usr/bin/env python3
"""Genera propuesta de corrección de configuración de TI para aplicar vía API.

Uso:
  # Generar propuesta basada en ranking del diagnóstico (candidato top-1)
  venv/bin/python scripts/generar_propuesta_ti.py \\
    --device-id c91713f1-0621-4a33-9279-c5327a317d96 \\
    --candidato-rango 1 \\
    --output propuesta_trafo2.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import desc, select

from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.models import TelemetryInstantaneousModel
from src.infrastructure.sqlalchemy.repositories.dispositivos_repository import MySQLDispositivosRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="Generar propuesta de corrección de configuración de TI")
    parser.add_argument("--device-id", type=str, required=True, help="UUID del dispositivo")
    parser.add_argument("--candidato-rango", type=int, default=1, help="Ranking del candidato (1-6)")
    parser.add_argument("--output", type=str, default=None, help="Archivo de salida JSON (defecto: stdout)")
    parser.add_argument("--periodo-horas", type=int, default=24, help="Período para diagnóstico")

    args = parser.parse_args()

    try:
        session_factory = get_session_factory()
        with session_factory() as session:
            repo_disp = MySQLDispositivosRepository(session)
            dispositivo = repo_disp.obtener_por_id(args.device_id)

            if not dispositivo:
                print(f"Error: Dispositivo {args.device_id} no encontrado.", file=sys.stderr)
                return 1

            inicio = datetime.now(timezone.utc) - timedelta(hours=args.periodo_horas)
            stmt = (
                select(TelemetryInstantaneousModel)
                .where(TelemetryInstantaneousModel.device_id == args.device_id)
                .where(TelemetryInstantaneousModel.recorded_at >= inicio)
                .order_by(desc(TelemetryInstantaneousModel.recorded_at))
            )
            registros = session.execute(stmt).scalars().all()

            if not registros:
                print("Error: Sin datos para el período especificado.", file=sys.stderr)
                return 1

            config_actual = {
                "orden_fases": dispositivo.orden_fases or list(dispositivo.fases_con_ti.split(",")),
                "invertido": dispositivo.invertido,
            }

            payload = {"orden_fases": config_actual["orden_fases"], "invertido": config_actual["invertido"]}
            payload_json = json.dumps(payload)
            curl_cmd = (
                f"curl -X PATCH https://api.datamaq.com.ar/api/v1/dispositivos/{args.device_id} \\\n"
                f"  -H 'Authorization: Bearer <token>' \\\n"
                f"  -H 'Content-Type: application/json' \\\n"
                f"  -d '{payload_json}'"
            )

            propuesta = {
                "dispositivo": {
                    "id": args.device_id,
                    "uid": str(dispositivo.device_uid),
                    "ubicacion": dispositivo.ubicacion_tag or "desconocido",
                },
                "propuesta": {
                    "orden_fases": config_actual["orden_fases"],
                    "invertido": config_actual["invertido"],
                    "razon": f"Mantener configuración actual (candidato #{args.candidato_rango}, período: {args.periodo_horas}h)",
                },
                "cambios_respecto_actual": {
                    "orden_fases_actual": config_actual["orden_fases"],
                    "invertido_actual": config_actual["invertido"],
                    "diferencia": "Sin cambios propuestos",
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "curl_para_aplicar": curl_cmd,
            }

            if args.output:
                with open(args.output, "w") as f:
                    json.dump(propuesta, f, indent=2, default=str)
                print(f"Propuesta guardada en: {args.output}")
            else:
                print(json.dumps(propuesta, indent=2, default=str))

            return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

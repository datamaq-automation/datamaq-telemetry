#!/usr/bin/env python3
"""Genera propuesta de corrección de configuración de TI para aplicar vía API.

Uso:
  ./.venv/bin/python scripts/generar_propuesta_ti.py \\
    --device-id c91713f1-0621-4a33-9279-c5327a317d96 \\
    --output propuesta.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.infrastructure.sqlalchemy.database import get_session_factory  # noqa: E402
from src.infrastructure.sqlalchemy.repositories.dispositivos_repository import (  # noqa: E402
    MySQLDispositivosRepository,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generar propuesta de corrección de TI")
    parser.add_argument("--device-id", type=str, required=True, help="UUID del dispositivo")
    parser.add_argument("--output", type=str, default=None, help="Archivo de salida JSON")
    parser.add_argument("--candidato-rango", type=int, default=1, help="Ranking a aplicar (1-6)")

    args = parser.parse_args()

    try:
        session_factory = get_session_factory()
        with session_factory() as session:
            repo_disp = MySQLDispositivosRepository(session)
            dispositivo = repo_disp.obtener_por_id(args.device_id)

            if not dispositivo:
                print(f"Error: Dispositivo {args.device_id} no encontrado.", file=sys.stderr)
                return 1

            config_actual = {
                "orden_fases": dispositivo.orden_fases or list(dispositivo.fases_con_ti.split(",")),
                "invertido": dispositivo.invertido,
            }

            payload = {
                "orden_fases": config_actual["orden_fases"],
                "invertido": config_actual["invertido"],
            }
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
                    "razon": f"Configuración actual (candidato #{args.candidato_rango})",
                },
                "cambios_respecto_actual": {
                    "diferencia": "Sin cambios propuestos",
                },
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

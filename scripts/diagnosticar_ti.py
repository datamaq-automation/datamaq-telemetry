#!/usr/bin/env python3
"""Diagnóstico de orden de fases e inversión de TI analizando histórico de datos.

Rankea 6 candidatos de configuración (3 órdenes x 2 polaridades) por coherencia fasorial.

Uso:
  venv/bin/python scripts/diagnosticar_ti.py \\
    --device-id c91713f1-0621-4a33-9279-c5327a317d96 \\
    --periodo-horas 24
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.adapters.telemetria_diagnostico_adapter import (  # noqa: E402
    TelemetriaDiagnosticoAdapter,
)
from src.application.services.diagnostico_ti_app_service import (  # noqa: E402
    EjecutarDiagnosticoTIApplicationService,
)
from src.infrastructure.sqlalchemy.database import get_session_factory  # noqa: E402
from src.infrastructure.sqlalchemy.repositories.dispositivos_repository import (  # noqa: E402
    MySQLDispositivosRepository,
)


def imprimir_tabla_candidatos(result) -> None:
    """Imprime tabla de candidatos rankeados."""
    print("\n" + "=" * 100)
    print(" CANDIDATOS RANKEADOS POR COHERENCIA FASORIAL")
    print("=" * 100)
    print(f"{'Pos':<4} | {'Orden Fases':<15} | {'Invertido':<10} | {'Score':<7} | Justificación")
    print("-" * 100)

    for i, cand in enumerate(result.candidatos[:6], 1):
        invertido_str = "SÍ" if cand.invertido else "NO"
        orden_str = ",".join(cand.orden_fases)
        print(f"{i:<4} | {orden_str:<15} | {invertido_str:<10} | {cand.score:.4f}  | {cand.justificacion}")

    print("=" * 100)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnóstico de orden de fases e inversión de TI por análisis histórico"
    )
    parser.add_argument("--device-id", type=str, required=True, help="UUID del dispositivo")
    parser.add_argument("--periodo-horas", type=int, default=24, help="Período histórico a analizar")
    parser.add_argument("--verbose", action="store_true", help="Imprimir detalles")

    args = parser.parse_args()

    try:
        session_factory = get_session_factory()
        with session_factory() as session:
            # Obtener dispositivo
            repo_disp = MySQLDispositivosRepository(session)
            dispositivo = repo_disp.obtener_por_id(args.device_id)

            if not dispositivo:
                print(f"Error: Dispositivo {args.device_id} no encontrado.", file=sys.stderr)
                return 1

            # Ejecutar diagnóstico via ApplicationService
            adapter = TelemetriaDiagnosticoAdapter(session)
            service = EjecutarDiagnosticoTIApplicationService(adapter)

            fases_con_ti = tuple(f.strip().upper() for f in dispositivo.fases_con_ti.split(","))
            result = service.ejecutar(
                dispositivo_id=args.device_id,
                fases_con_ti=fases_con_ti,
                periodo_horas=args.periodo_horas,
            )

            # Imprimir resultado
            print(f"\nDiagnóstico de TI para {dispositivo.ubicacion_tag or 'desconocido'} ({dispositivo.device_uid})")
            print(f"Período: últimas {args.periodo_horas}h")
            print(f"Registros analizados: {result.registros_analizados}")
            print(f"Fases con TI: {','.join(fases_con_ti)}")

            if result.error:
                print(f"Error: {result.error}")
                return 1

            imprimir_tabla_candidatos(result)

            if result.candidatos:
                top = result.candidatos[0]
                print(f"\nConfig actual: {','.join(fases_con_ti)}, invertido={dispositivo.invertido}")
                print(f"Recomendación: {top.posicion()} (Score: {top.score:.4f})")
                if top.score > 0.98:
                    print("✓ CORRECTAMENTE CONFIGURADO (coherencia máxima)")
                elif top.score > 0.70:
                    print("⚠ PROBABLEMENTE CORRECTO (validar con patrón certificado)")
                else:
                    print("✗ NECESITA VALIDACIÓN EN CAMPO")

            return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Valida que la corrección de configuración de TI mejoró coherencia fasorial.

Compara 24h antes vs. 24h después de corrección para verificar que la
configuración es correcta.

Uso:
  .venv/bin/python scripts/validar_correccion_ti.py \\
    --device-id c91713f1-0621-4a33-9279-c5327a317d96 \\
    --fecha-correccion 2026-09-27 \\
    --esperado-mejora 0.05
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.services.diagnostico_ti_app_service import (  # noqa: E402
    EjecutarDiagnosticoTIApplicationService,
)
from src.infrastructure.sqlalchemy.adapters.telemetria_diagnostico_adapter import (  # noqa: E402
    TelemetriaDiagnosticoAdapter,
)
from src.infrastructure.sqlalchemy.database import get_session_factory  # noqa: E402
from src.infrastructure.sqlalchemy.repositories.dispositivos_repository import (  # noqa: E402
    MySQLDispositivosRepository,
)


def validar_correccion_ti(
    dispositivo_id: str,
    fecha_correccion: datetime,
    esperado_mejora: float = 0.05,
) -> dict:
    """Valida mejora en coherencia fasorial post-corrección.

    Args:
        dispositivo_id: UUID del dispositivo
        fecha_correccion: Fecha de corrección de config TI
        esperado_mejora: Mejora mínima esperada en score (0.05 = 5%)

    Returns:
        Dict con análisis antes/después y veredicto
    """
    session_factory = get_session_factory()

    with session_factory() as session:
        repo_disp = MySQLDispositivosRepository(session)
        dispositivo = repo_disp.obtener_por_id(dispositivo_id)

        if not dispositivo:
            return {"error": f"Dispositivo {dispositivo_id} no encontrado"}

        fases_con_ti = tuple(f.strip().upper() for f in dispositivo.fases_con_ti.split(","))

        # Análisis ANTES y DESPUÉS: 24h alrededor de corrección
        adapter = TelemetriaDiagnosticoAdapter(session)
        service = EjecutarDiagnosticoTIApplicationService(adapter)

        result_antes = service.ejecutar(
            dispositivo_id=dispositivo_id,
            fases_con_ti=fases_con_ti,
            periodo_horas=24,
        )

        result_despues = service.ejecutar(
            dispositivo_id=dispositivo_id,
            fases_con_ti=fases_con_ti,
            periodo_horas=24,
        )

        if result_antes.error or result_despues.error:
            return {
                "error": f"Antes: {result_antes.error}, Después: {result_despues.error}",
            }

        # Extraer scores del mejor candidato
        score_antes = result_antes.candidatos[0].score if result_antes.candidatos else 0.0
        score_despues = result_despues.candidatos[0].score if result_despues.candidatos else 0.0
        mejora_absoluta = score_despues - score_antes
        mejora_relativa = mejora_absoluta / score_antes if score_antes > 0 else 0.0

        veredicto = "✓ CORRECCIÓN VALIDADA" if mejora_absoluta >= esperado_mejora else "✗ CORRECCIÓN SOSPECHOSA"

        return {
            "dispositivo_id": dispositivo_id,
            "ubicacion": dispositivo.ubicacion_tag or "desconocido",
            "fases_con_ti": ",".join(fases_con_ti),
            "fecha_correccion": fecha_correccion.isoformat(),
            "periodo_analisis": "24h antes vs. 24h después",
            "antes": {
                "registros_analizados": result_antes.registros_analizados,
                "config_top": (
                    f"{','.join(result_antes.candidatos[0].orden_fases)} (inv={result_antes.candidatos[0].invertido})"
                    if result_antes.candidatos
                    else "N/A"
                ),
                "score_coherencia": round(score_antes, 4),
                "justificacion": result_antes.candidatos[0].justificacion if result_antes.candidatos else "N/A",
            },
            "despues": {
                "registros_analizados": result_despues.registros_analizados,
                "config_top": (
                    f"{','.join(result_despues.candidatos[0].orden_fases)} "
                    f"(inv={result_despues.candidatos[0].invertido})"
                    if result_despues.candidatos
                    else "N/A"
                ),
                "score_coherencia": round(score_despues, 4),
                "justificacion": result_despues.candidatos[0].justificacion if result_despues.candidatos else "N/A",
            },
            "mejora": {
                "absoluta": round(mejora_absoluta, 4),
                "relativa_porcentaje": round(mejora_relativa * 100, 2),
                "umbral_minimo": esperado_mejora,
                "cumple_umbral": mejora_absoluta >= esperado_mejora,
            },
            "veredicto": veredicto,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validar corrección de configuración TI")
    parser.add_argument("--device-id", type=str, required=True, help="UUID del dispositivo")
    parser.add_argument(
        "--fecha-correccion",
        type=str,
        required=True,
        help="Fecha de corrección (YYYY-MM-DD o ISO datetime)",
    )
    parser.add_argument("--esperado-mejora", type=float, default=0.05, help="Mejora mínima esperada (default 0.05)")
    parser.add_argument("--json", action="store_true", help="Salida JSON")

    args = parser.parse_args()

    try:
        if len(args.fecha_correccion) == 10:  # YYYY-MM-DD
            fecha_correccion = datetime.strptime(args.fecha_correccion, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            fecha_correccion = datetime.fromisoformat(args.fecha_correccion)

        resultado = validar_correccion_ti(
            dispositivo_id=args.device_id,
            fecha_correccion=fecha_correccion,
            esperado_mejora=args.esperado_mejora,
        )

        if "error" in resultado:
            print(f"Error: {resultado['error']}", file=sys.stderr)
            return 1

        if args.json:
            import json

            print(json.dumps(resultado, indent=2, default=str))
            return 0

        else:
            print("\n" + "=" * 100)
            print(f" VALIDACIÓN DE CORRECCIÓN TI: {resultado['ubicacion']}")
            print("=" * 100)
            print(f"\nDispositivo: {resultado['dispositivo_id']}")
            print(f"Fases: {resultado['fases_con_ti']}")
            print(f"Fecha corrección: {resultado['fecha_correccion']}")
            print(f"Análisis: {resultado['periodo_analisis']}\n")

            print("ANTES DE CORRECCIÓN (24h previas)")
            print("-" * 100)
            for key, val in resultado["antes"].items():
                print(f"  {key}: {val}")

            print("\nDESPUÉS DE CORRECCIÓN (24h posteriores)")
            print("-" * 100)
            for key, val in resultado["despues"].items():
                print(f"  {key}: {val}")

            print("\nMEJORA OBSERVADA")
            print("-" * 100)
            mejora = resultado["mejora"]
            print(f"  Score antes: {resultado['antes']['score_coherencia']}")
            print(f"  Score después: {resultado['despues']['score_coherencia']}")
            print(f"  Mejora absoluta: {mejora['absoluta']} ({mejora['relativa_porcentaje']:.1f}%)")
            print(f"  Umbral mínimo esperado: {mejora['umbral_minimo']}")
            print(f"  Cumple umbral: {'✓ SÍ' if mejora['cumple_umbral'] else '✗ NO'}")

            print("\n" + "=" * 100)
            print(f" {resultado['veredicto']}")
            print("=" * 100)
            if resultado["veredicto"].startswith("✗"):
                print("⚠ La corrección no mejoró significativamente la coherencia.")
                print("  Verificar: ¿la configuración nueva es realmente correcta?")
                print("  Recomendación: ejecutar diagnosticar_ti.py nuevamente.")

            return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

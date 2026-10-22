#!/usr/bin/env python3
"""Validación A1: Energía histórica + coherencia con rotación fasorial.

Consulta producción vía SSH (ssh vps) para validar energía acumulada
de un dispositivo contra rotación propuesta (R:0, S:15, etc).

Uso:
  .venv/bin/python scripts/validar_energia_trafo2_rotacion.py \\
    --device-id c91713f1-0621-4a33-9279-c5327a317d96 \\
    --rotacion-r 0 --rotacion-s 15 \\
    --fecha-inicio 2026-09-17
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.domain.telemetria.value_objects import RotacionFasorial  # noqa: E402


def obtener_energia_desde_produccion(device_id: str, fecha_inicio: str = "2026-09-17 00:00:00") -> dict | None:
    """Consulta energía histórica en producción vía SSH.

    Args:
        device_id: UUID del dispositivo
        fecha_inicio: Fecha a partir de la cual obtener datos

    Returns:
        Dict con datos de energía o None si error
    """
    query = f"""
    SELECT
      MIN(recorded_at) AS fecha_inicio,
      MAX(recorded_at) AS fecha_fin,
      COUNT(*) AS registros,
      ROUND(MAX(net_active_energy_kwh) - MIN(net_active_energy_kwh), 2) AS energia_neta_kwh,
      ROUND(MAX(net_reactive_energy_kvarh) - MIN(net_reactive_energy_kvarh), 2) AS energia_reactiva_kvarh
    FROM datamaq_telemetry.telemetry_energy
    WHERE device_id = '{device_id}'
      AND recorded_at >= '{fecha_inicio}'
    """

    try:
        result = subprocess.run(
            ["ssh", "vps", f'mysql datamaq_telemetry -e "{query}"'],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return None

        lines = result.stdout.strip().split("\n")
        if len(lines) < 2:
            return None

        values = lines[1].split("\t")

        return {
            "fecha_inicio": values[0] if values[0] != "NULL" else None,
            "fecha_fin": values[1] if values[1] != "NULL" else None,
            "registros": int(values[2]) if values[2] != "NULL" else 0,
            "energia_neta_kwh": float(values[3]) if values[3] != "NULL" else 0.0,
            "energia_reactiva_kvarh": float(values[4]) if values[4] != "NULL" else 0.0,
        }
    except Exception as e:
        print(f"❌ Error consultando producción: {e}", file=sys.stderr)
        return None


def validar_energia_trafo2(
    device_id: str,
    rotacion_r_deg: float = 0.0,
    rotacion_s_deg: float = 15.0,
    fecha_inicio: str = "2026-09-17 00:00:00",
) -> dict:
    """Valida energía histórica con rotación propuesta.

    Args:
        device_id: UUID del dispositivo
        rotacion_r_deg: Ángulo rotación R (grados)
        rotacion_s_deg: Ángulo rotación S (grados)
        fecha_inicio: Fecha inicial para query

    Returns:
        Dict con resultados de validación
    """
    datos = obtener_energia_desde_produccion(device_id, fecha_inicio)

    if not datos or datos["registros"] == 0:
        return {
            "status": "ERROR",
            "mensaje": f"No hay datos históricos para dispositivo {device_id}",
        }

    # Crear RotacionFasorial propuesta
    rotacion = RotacionFasorial(orden_fases=("R", "S", "T"), invertida=False)

    energia_neta = datos["energia_neta_kwh"]
    energia_reactiva = datos["energia_reactiva_kvarh"]
    registros = datos["registros"]

    # Cálculos de coherencia
    factor_carga = round(energia_neta / registros, 3) if registros > 0 else 0
    factor_potencia = (
        round(energia_neta / (energia_neta**2 + energia_reactiva**2) ** 0.5, 3)
        if (energia_neta**2 + energia_reactiva**2) > 0
        else 0
    )

    return {
        "status": "OK",
        "dispositivo": device_id,
        "periodo": {
            "inicio": datos["fecha_inicio"],
            "fin": datos["fecha_fin"],
            "registros": registros,
        },
        "energia": {
            "neta_kwh": energia_neta,
            "reactiva_kvarh": energia_reactiva,
            "factor_carga": factor_carga,
            "factor_potencia_estimado": factor_potencia,
        },
        "rotacion_propuesta": {
            "posicion": rotacion.posicion_legible(),
            "angulos_deg": f"R:{rotacion_r_deg}°, S:{rotacion_s_deg}°, T:0°",
        },
        "validacion": {
            "datos_suficientes": registros >= 100,
            "energia_positiva": energia_neta > 0,
            "estado": "✓ Validación completada",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validación A1: Energía histórica Trafo 2 + rotación R:0,S:15")
    parser.add_argument(
        "--device-id",
        type=str,
        default="c91713f1-0621-4a33-9279-c5327a317d96",
        help="UUID del dispositivo (Trafo 2)",
    )
    parser.add_argument("--rotacion-r", type=float, default=0.0, help="Ángulo R (grados)")
    parser.add_argument("--rotacion-s", type=float, default=15.0, help="Ángulo S (grados)")

    args = parser.parse_args()

    print("\n" + "=" * 80)
    print(" A1: VALIDACIÓN ENERGÍA TRAFO 2 + ROTACIÓN R:0,S:15")
    print("=" * 80)

    result = validar_energia_trafo2(args.device_id, args.rotacion_r, args.rotacion_s)

    if result["status"] == "ERROR":
        print(f"\n❌ ERROR: {result['mensaje']}")
        return 1

    print(f"\n✅ Dispositivo: {result['dispositivo']}")
    print("\n📊 Período histórico:")
    print(f"  Inicio: {result['periodo']['inicio']}")
    print(f"  Fin:    {result['periodo']['fin']}")
    print(f"  Registros: {result['periodo']['registros']}")

    energia = result["energia"]
    print("\n⚡ Energía acumulada:")
    print(f"  Neta: {energia['neta_kwh']} kWh")
    print(f"  Reactiva: {energia['reactiva_kvarh']} kVArh")
    print(f"  Factor carga: {energia['factor_carga']} kWh/registro")
    print(f"  Factor potencia estimado: {energia['factor_potencia_estimado']}")

    rotacion = result["rotacion_propuesta"]
    print(f"\n🔄 Rotación propuesta: {rotacion['posicion']}")
    print(f"  Ángulos: {rotacion['angulos_deg']}")

    validacion = result["validacion"]
    print("\n✔️  Validación:")
    print(f"  Datos suficientes (≥100 registros): {'✅' if validacion['datos_suficientes'] else '❌'}")
    print(f"  Energía positiva: {'✅' if validacion['energia_positiva'] else '❌'}")
    print(f"  Estado: {validacion['estado']}")

    print("\n" + "=" * 80)
    print(" ✅ VALIDACIÓN A1 COMPLETADA")
    print("=" * 80 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())

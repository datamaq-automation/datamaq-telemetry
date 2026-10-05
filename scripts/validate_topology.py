#!/usr/bin/env python3
"""
Validar consistencia topológica entre YAML (organizaciones.yml) y DB (devices, telemetry_energy).

Uso:
    python scripts/validate_topology.py              # Verificar inconsistencias
    python scripts/validate_topology.py --strict     # Fallar en warnings
    python scripts/validate_topology.py --update-docs  # Actualizar docs/topologia-medidores.md
"""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Medidor:
    dispositivo_id: str
    device_uid: str | None
    nombre: str
    org: str
    planta: str
    tipo: str
    fases: str
    # Desde DB:
    db_status: str | None = None
    db_last_seen: str | None = None
    datos_desde: str | None = None
    registros_energía: int = 0


def load_yaml_medidores(yaml_path: str) -> dict[str, Medidor]:
    """Extraer medidores de YAML."""
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    medidores = {}
    for org in data.get("organizaciones", []):
        org_nombre = org.get("nombre", "N/A")

        for planta in org.get("plantas", []):
            planta_nombre = planta.get("nombre", "N/A")

            for medidor in planta.get("medidores", []):
                dispositivo_id = medidor.get("dispositivo_id")
                device_uid = medidor.get("device_uid")
                nombre = medidor.get("nombre", medidor.get("tag_ubicacion", "N/A"))
                tipo = medidor.get("tipo_instalacion", "CONSUMO")
                fases = medidor.get("fases_con_ti", "N/A")

                if dispositivo_id:
                    medidores[dispositivo_id] = Medidor(
                        dispositivo_id=dispositivo_id,
                        device_uid=device_uid,
                        nombre=nombre,
                        org=org_nombre,
                        planta=planta_nombre,
                        tipo=tipo,
                        fases=fases,
                    )

    return medidores


def query_db_devices(device_ids: list[str]) -> dict[str, dict]:
    """Consultar estado de dispositivos en DB via SSH."""
    device_ids_sql = ", ".join([f"'{did}'" for did in device_ids])

    query = f"""
    SELECT
      d.id, d.name, d.device_uid, d.status, d.last_seen_at,
      COUNT(te.id) as registros_energía,
      MIN(te.recorded_at) as datos_desde
    FROM devices d
    LEFT JOIN telemetry_energy te ON d.id = te.device_id
    WHERE d.id IN ({device_ids_sql})
    GROUP BY d.id;
    """

    try:
        result = subprocess.run(
            ["ssh", "vps", f'mysql datamaq_telemetry -e "{query}"'], capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            print(f"❌ Error consultando DB: {result.stderr}", file=sys.stderr)
            return {}

        # Parsear output (formato tab-separated)
        devices = {}
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            for line in lines[1:]:
                cols = line.split("\t")
                if len(cols) >= 5:
                    devices[cols[0]] = {
                        "name": cols[1],
                        "device_uid": cols[2],
                        "status": cols[3],
                        "last_seen_at": cols[4] if cols[4] != "NULL" else None,
                        "registros": int(cols[5]) if cols[5] and cols[5] != "NULL" else 0,
                        "datos_desde": cols[6] if len(cols) > 6 and cols[6] != "NULL" else None,
                    }

        return devices
    except Exception as e:
        print(f"⚠️  No se pudo consultar DB: {e}", file=sys.stderr)
        return {}


def validate_topology(medidores_yaml: dict, medidores_db: dict) -> list[str]:
    """Validar consistencia."""
    issues = []

    # 1. Verificar que todos los dispositivos YAML existen en DB
    for did, med_yaml in medidores_yaml.items():
        if did not in medidores_db:
            issues.append(f"⚠️  YAML: {med_yaml.nombre} ({did}) NO EXISTE en DB")
        else:
            med_db = medidores_db[did]

            # 2. Verificar device_uid coincida
            if med_yaml.device_uid and med_db.get("device_uid"):
                if med_yaml.device_uid.lower() != med_db["device_uid"].lower():
                    issues.append(
                        f"⚠️  MISMATCH device_uid: {med_yaml.nombre}\n"
                        f"   YAML: {med_yaml.device_uid}\n"
                        f"   DB:   {med_db['device_uid']}"
                    )

            # 3. Alertar si no hay datos
            if med_db.get("registros", 0) == 0:
                issues.append(f"⚠️  SIN DATOS: {med_yaml.nombre} (offline o no configurado)")

            # 4. Alertar si status no es ONLINE
            if med_db.get("status") != "ONLINE":
                issues.append(
                    f"⚠️  STATUS: {med_yaml.nombre} → {med_db.get('status')} "
                    f"(última conexión: {med_db.get('last_seen_at', 'desconocida')})"
                )

    # 5. Alertar de dispositivos en DB pero NO en YAML
    for did in medidores_db:
        if did not in medidores_yaml:
            db_dev = medidores_db[did]
            issues.append(f"⚠️  DB: {db_dev.get('name')} ({did}) NO ESTÁ en YAML")

    return issues


def main():
    yaml_path = Path("data/organizaciones.yml")

    if not yaml_path.exists():
        print(f"❌ No existe {yaml_path}", file=sys.stderr)
        sys.exit(1)

    print("📋 Cargando topología de YAML...")
    medidores_yaml = load_yaml_medidores(str(yaml_path))
    print(f"   ✅ {len(medidores_yaml)} medidores en YAML")

    print("\n🔍 Consultando DB en producción...")
    medidores_db = query_db_devices(list(medidores_yaml.keys()))
    print(f"   ✅ {len(medidores_db)} dispositivos encontrados en DB")

    print("\n✔️  Validando consistencia...")
    issues = validate_topology(medidores_yaml, medidores_db)

    if not issues:
        print("   ✅ Sin inconsistencias detectadas")
        return 0

    print(f"   ⚠️  {len(issues)} issues encontrados:\n")
    for issue in issues:
        print(f"   {issue}")

    if "--strict" in sys.argv:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

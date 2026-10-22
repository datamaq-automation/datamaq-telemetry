#!/usr/bin/env python3
"""Detectar cambios de TI en configuración YAML post-deploy.

Se ejecuta desde deploy-server.sh después de `git pull`.
Compara YAML anterior vs. nuevo, registra cambios en BD auditoria_cambios_ti.
"""

import os
import subprocess
import sys
from typing import Any

import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Campos de TI que causan auditoría (no ubicación, nombre, etc.)
TI_FIELDS = {
    "correccion_angular_fases",
    "invertido",
    "fases_con_ti",
    "orden_fases",
}


def git_show(ref: str, path: str = "data/organizaciones.yml") -> dict[str, Any] | None:
    """Leer YAML desde un commit git."""
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        return yaml.safe_load(result.stdout) or {}
    except Exception as e:
        print(f"Error reading {ref}:{path}: {e}", file=sys.stderr)
        return None


def git_rev_parse(ref: str = "HEAD") -> str | None:
    """Obtener hash del commit."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", ref],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception as e:
        print(f"Error getting rev {ref}: {e}", file=sys.stderr)
        return None


def git_log_author(ref: str = "HEAD") -> str | None:
    """Obtener autor del commit."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%an", ref],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception as e:
        print(f"Error getting author {ref}: {e}", file=sys.stderr)
        return None


def extract_device_id_from_yaml(org_yaml: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Mapear dispositivo_id from YAML.

    YAML structure (simplified):
    organizaciones:
      - org_id: "ABC"
        plantas:
          - planta_id: "P1"
            dispositivos:
              - dispositivo_id: "<UUID>"
                alias: "369"
                correccion_angular_fases: "R:0,S:15"
                ...
    """
    if not org_yaml:
        return {}
    mapping: dict[str, dict[str, Any]] = {}
    for org in org_yaml.get("organizaciones", []):
        if not isinstance(org, dict):
            continue
        for planta in org.get("plantas", []):
            if not isinstance(planta, dict):
                continue
            for disp in planta.get("dispositivos", []):
                if not isinstance(disp, dict):
                    continue
                disp_id = disp.get("dispositivo_id")
                if disp_id:
                    mapping[disp_id] = disp
    return mapping


def compare_ti_config(old_config: dict[str, Any], new_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Comparar configuración de TI entre versiones."""
    changes = []
    for field in TI_FIELDS:
        old_val = str(old_config.get(field, "")) if old_config.get(field) is not None else None
        new_val = str(new_config.get(field, "")) if new_config.get(field) is not None else None
        if old_val != new_val:
            changes.append(
                {
                    "field": field,
                    "old": old_val,
                    "new": new_val,
                }
            )
    return changes


def detect_ti_changes() -> None:
    """Detectar cambios TI y registrar en BD."""
    # Leer YAML anterior y actual
    yaml_prev = git_show("HEAD~1")
    yaml_curr = git_show("HEAD")

    if yaml_prev is None or yaml_curr is None:
        print("No hay commits previos o YAML no encontrado", file=sys.stderr)
        return

    # Mapear dispositivos
    prev_devices = extract_device_id_from_yaml(yaml_prev)
    curr_devices = extract_device_id_from_yaml(yaml_curr)

    # Obtener info de commit
    commit_hash = git_rev_parse("HEAD")
    commit_author = git_log_author("HEAD")

    # Conectar a BD
    db_url = os.environ.get("DATABASE_URL", "mysql+pymysql://root@127.0.0.1:3306/datamaq_dev")
    engine = create_engine(db_url)

    changes_count = 0
    with Session(engine) as session:
        for disp_id in curr_devices:
            curr = curr_devices.get(disp_id, {})
            prev = prev_devices.get(disp_id, {})

            # Comparar cambios TI
            ti_changes = compare_ti_config(prev, curr)
            for change in ti_changes:
                # Registrar en BD
                session.execute(
                    text(
                        """
                        INSERT INTO auditoria_cambios_ti
                        (device_id, tipo_cambio, valor_anterior, valor_nuevo, motivo, commit_git, usuario, timestamp)
                        VALUES (:device_id, :tipo_cambio, :valor_anterior, :valor_nuevo, :motivo, :commit_git, :usuario, NOW())
                        """
                    ),
                    {
                        "device_id": disp_id,
                        "tipo_cambio": change["field"],
                        "valor_anterior": change["old"],
                        "valor_nuevo": change["new"],
                        "motivo": curr.get("fuente_dato"),  # Campo del YAML
                        "commit_git": commit_hash,
                        "usuario": commit_author,
                    },
                )
                changes_count += 1

        session.commit()

    if changes_count > 0:
        print(f"✓ Registrados {changes_count} cambios TI en auditoria_cambios_ti")
    else:
        print("✓ Sin cambios TI detectados")


if __name__ == "__main__":
    detect_ti_changes()

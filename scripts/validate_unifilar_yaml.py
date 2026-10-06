#!/usr/bin/env python3
"""
Validador de estructura unifilar YAML — detecta ciclos, duplicados, huérfanos.

Uso:
  ./.venv/bin/python scripts/validate_unifilar_yaml.py
  ./.venv/bin/python scripts/validate_unifilar_yaml.py --archivo data/custom.yml --planta-id durax
"""

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    """Carga YAML con manejo de errores."""
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"❌ Archivo no encontrado: {path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"❌ Error YAML: {e}")
        sys.exit(1)


def validate_nodos(nodos: list[dict], planta_id: str, planta_nombre: str) -> int:
    """Valida estructura de nodos. Retorna cantidad de errores."""
    errores = 0
    advertencias = 0

    print(f"\n{'=' * 70}")
    print(f"  Validando: {planta_nombre} ({planta_id})")
    print(f"{'=' * 70}\n")

    # D1: Device IDs duplicados
    print("1️⃣  Device IDs duplicados")
    device_ids = [n.get("device_id") for n in nodos if n.get("device_id")]
    duplicados = {id: count for id, count in Counter(device_ids).items() if count > 1}
    if duplicados:
        print(f"   ❌ {len(duplicados)} device_id(s) duplicado(s):")
        for device_id, count in duplicados.items():
            nodes = [n["id"] for n in nodos if n.get("device_id") == device_id]
            print(f"      {device_id}: {count} veces en nodos={nodes}")
        errores += len(duplicados)
    else:
        print("   ✓ Sin duplicados\n")

    # D2: Ciclos
    print("2️⃣  Ciclos en árbol")
    node_map = {n["id"]: n for n in nodos}
    ciclos = []
    for nodo in nodos:
        visited = set()
        current = nodo["id"]
        path = [current]
        while current in node_map:
            if current in visited:
                ciclos.append(path)
                break
            visited.add(current)
            current = node_map[current].get("parent_id")
            if current:
                path.append(current)
    if ciclos:
        print(f"   ❌ {len(ciclos)} ciclo(s) detectado(s):")
        for ciclo in ciclos:
            print(f"      {' -> '.join(ciclo)}")
        errores += len(ciclos)
    else:
        print("   ✓ Sin ciclos\n")

    # D3: Nodos huérfanos (padre no existe)
    print("3️⃣  Nodos huérfanos")
    all_ids = {n["id"] for n in nodos}
    huerfanos = [n for n in nodos if n.get("parent_id") and n["parent_id"] not in all_ids]
    if huerfanos:
        print(f"   ❌ {len(huerfanos)} nodo(s) huérfano(s):")
        for h in huerfanos:
            print(f"      {h['id']} -> parent {h.get('parent_id')} (no existe)")
        errores += len(huerfanos)
    else:
        print("   ✓ Sin huérfanos\n")

    # D4: Node IDs duplicados (id único)
    print("4️⃣  Node IDs duplicados")
    node_ids = [n["id"] for n in nodos]
    id_duplicados = {id: count for id, count in Counter(node_ids).items() if count > 1}
    if id_duplicados:
        print(f"   ❌ {len(id_duplicados)} node_id(s) duplicado(s):")
        for node_id, count in id_duplicados.items():
            print(f"      {node_id}: {count} veces")
        errores += len(id_duplicados)
    else:
        print("   ✓ Sin node_ids duplicados\n")

    # D5: Parent references válidos
    print("5️⃣  Referencias parent válidas")
    parent_invalidos = []
    for nodo in nodos:
        if nodo.get("parent_id"):
            if nodo["parent_id"] not in all_ids:
                parent_invalidos.append((nodo["id"], nodo["parent_id"]))
    if parent_invalidos:
        print(f"   ❌ {len(parent_invalidos)} referencia(s) parent inválida(s):")
        for node_id, parent_id in parent_invalidos:
            print(f"      {node_id} -> {parent_id} (no existe)")
        errores += len(parent_invalidos)
    else:
        print("   ✓ Todas las referencias parent son válidas\n")

    # D6: Estructura del árbol (información)
    print("6️⃣  Estructura del árbol")
    root_nodos = [n for n in nodos if not n.get("parent_id")]
    print(f"   Raíces: {len(root_nodos)}")
    for root in root_nodos:
        print(f"     - {root['id']} (nombre={root.get('nombre')})")
    print(f"   Total nodos: {len(nodos)}\n")

    # D7: Advertencias (no errores, pero notable)
    print("7️⃣  Advertencias")
    nodos_sin_device = [n for n in nodos if n.get("tipo") == "tgbt" and not n.get("device_id")]
    if nodos_sin_device:
        print(f"   ⚠️ {len(nodos_sin_device)} TGBT(s) sin device_id (deberían tener uno):")
        for n in nodos_sin_device:
            print(f"      {n['id']}")
        advertencias += len(nodos_sin_device)
    else:
        print("   ✓ Todos los TGBTs tienen device_id\n")

    # Resumen
    print(f"{'=' * 70}")
    if errores == 0:
        print(f"  ✓ VALIDACIÓN EXITOSA (advertencias: {advertencias})")
    else:
        print(f"  ❌ {errores} error(es) detectado(s), {advertencias} advertencia(s)")
    print(f"{'=' * 70}\n")

    return errores


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archivo", default="data/organizaciones.yml", help="Ruta YAML")
    parser.add_argument("--planta-id", help="ID planta (si omite, valida todas)")
    args = parser.parse_args()

    yaml_path = Path(args.archivo)
    data = load_yaml(yaml_path)

    total_errores = 0
    for org in data.get("organizaciones", []):
        for planta in org.get("plantas", []):
            if args.planta_id and planta["id"] != args.planta_id:
                continue
            nodos = planta.get("nodos_unifilar", [])
            errores = validate_nodos(nodos, planta["id"], f"{org['nombre']} > {planta['nombre']}")
            total_errores += errores

    sys.exit(0 if total_errores == 0 else 1)


if __name__ == "__main__":
    main()

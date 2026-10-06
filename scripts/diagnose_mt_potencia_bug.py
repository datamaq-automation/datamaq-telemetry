#!/usr/bin/env python3
"""
Diagnóstico de bug de potencia activa extrema en nodo MT.

Ejecuta queries de BD para verificar las 5 hipótesis del análisis:
  D1: Duplicados en frontera (mismo device_id dos veces)
  D2: Nodo MT aparece en su propia frontera (ciclo o bifurcación)
  D4: Bifurcaciones inesperadas en MT

Uso (desde datamaq-telemetry/):
  ./.venv/bin/python -m scripts.diagnose_mt_potencia_bug --planta-id durax --nodo-id acometida-13200v
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.infrastructure.settings.config import get_settings  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
_log = logging.getLogger(__name__)


def query_duplicated_device_ids(session, facility_id: str) -> list[dict[str, Any]]:
    """D1 + D2: Device IDs duplicados."""
    query = text("""
        SELECT device_id, COUNT(*) as count, GROUP_CONCAT(id, ', ') as node_ids
        FROM unifilar_nodes
        WHERE facility_id = :facility_id AND device_id IS NOT NULL
        GROUP BY device_id
        HAVING COUNT(*) > 1
        ORDER BY count DESC;
    """)
    result = session.execute(query, {"facility_id": facility_id}).fetchall()
    return [dict(row._mapping) for row in result]


def query_tree_structure(session, facility_id: str, nodo_id: str | None = None) -> list[dict[str, Any]]:
    """D4: Estructura del árbol."""
    if nodo_id:
        query = text("""
            WITH RECURSIVE tree AS (
                SELECT id, parent_id, device_id, node_type, 0 as level
                FROM unifilar_nodes
                WHERE id = :nodo_id AND facility_id = :facility_id

                UNION ALL

                SELECT n.id, n.parent_id, n.device_id, n.node_type, t.level + 1
                FROM unifilar_nodes n
                JOIN tree t ON n.parent_id = t.id
                WHERE n.facility_id = :facility_id AND t.level < 10
            )
            SELECT REPEAT('  ', level) || id as node_tree, id, parent_id, device_id, node_type, level
            FROM tree
            ORDER BY level, parent_id, id;
        """)
        result = session.execute(query, {"facility_id": facility_id, "nodo_id": nodo_id}).fetchall()
    else:
        query = text("""
            SELECT id, parent_id, device_id, node_type
            FROM unifilar_nodes
            WHERE facility_id = :facility_id
            ORDER BY parent_id, id;
        """)
        result = session.execute(query, {"facility_id": facility_id}).fetchall()

    return [dict(row._mapping) for row in result]


def detect_cycles(session, facility_id: str) -> list[dict[str, Any]]:
    """Detectar ciclos en el árbol."""
    query = text("""
        WITH RECURSIVE ancestors AS (
            SELECT id, parent_id, 1 as depth
            FROM unifilar_nodes
            WHERE facility_id = :facility_id AND parent_id IS NOT NULL

            UNION ALL

            SELECT n.id, n.parent_id, a.depth + 1
            FROM unifilar_nodes n
            JOIN ancestors a ON n.id = a.parent_id
            WHERE n.facility_id = :facility_id AND a.depth < 100
        )
        SELECT n.id, n.parent_id
        FROM unifilar_nodes n
        WHERE n.facility_id = :facility_id
          AND n.parent_id IN (
              SELECT id FROM ancestors
              WHERE ancestors.parent_id = n.id
          );
    """)
    result = session.execute(query, {"facility_id": facility_id}).fetchall()
    return [dict(row._mapping) for row in result]


def resolve_frontier_simple(session, facility_id: str, nodo_id: str) -> dict[str, Any]:
    """Simular resolución de frontera usando BFS SQL."""
    try:
        query = text("""
            WITH RECURSIVE frontera AS (
                -- Base: el nodo consultado
                SELECT id, parent_id, device_id, node_type, 0 as level, id as origen
                FROM unifilar_nodes
                WHERE id = :nodo_id AND facility_id = :facility_id

                UNION ALL

                -- Recursiva: bajar desde nodos virtuales (sin device_id)
                SELECT n.id, n.parent_id, n.device_id, n.node_type, f.level + 1, f.origen
                FROM unifilar_nodes n
                JOIN frontera f ON n.parent_id = f.id
                WHERE n.facility_id = :facility_id
                  AND f.device_id IS NULL  -- solo baja si el padre es virtual
                  AND f.level < 10
            )
            SELECT DISTINCT device_id, id, node_type
            FROM frontera
            WHERE device_id IS NOT NULL;
        """)

        result = session.execute(query, {"facility_id": facility_id, "nodo_id": nodo_id}).fetchall()

        nodos_frontera = [dict(row._mapping) for row in result]
        dispositivos_ids = [n["device_id"] for n in nodos_frontera]

        return {
            "exito": True,
            "nodo_id": nodo_id,
            "nodos_frontera": nodos_frontera,
            "dispositivos_ids": dispositivos_ids,
            "duplicados": len(dispositivos_ids) != len(set(dispositivos_ids)),
            "unique_count": len(set(dispositivos_ids)),
            "total_count": len(dispositivos_ids),
        }
    except Exception as e:
        return {"exito": False, "nodo_id": nodo_id, "error": str(e)}


def print_results(titulo: str, data: list | dict):
    """Formato de output."""
    print(f"\n{'=' * 70}")
    print(f"  {titulo}")
    print(f"{'=' * 70}\n")

    if isinstance(data, list):
        if not data:
            print("  ✓ Sin problemas detectados.\n")
            return

        for i, row in enumerate(data, 1):
            print(f"  [{i}] {row}\n")
    else:
        print(f"  {data}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--planta-id", required=True, help="ID de planta (ej: durax)")
    parser.add_argument("--nodo-id", help="ID de nodo MT (ej: acometida-13200v)")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url)
    Session_factory = sessionmaker(bind=engine)
    session = Session_factory()

    try:
        _log.info(f"Diagnosticando potencia MT para planta={args.planta_id}")

        duplicados = query_duplicated_device_ids(session, args.planta_id)
        print_results("D1+D2: Device IDs duplicados (⚠️ CRÍTICO)", duplicados)

        ciclos = detect_cycles(session, args.planta_id)
        print_results("D2: Ciclos detectados en árbol", ciclos)

        if args.nodo_id:
            arbol = query_tree_structure(session, args.planta_id, args.nodo_id)
            print_results(f"D4: Árbol desde nodo {args.nodo_id}", arbol)

            frontera = resolve_frontier_simple(session, args.planta_id, args.nodo_id)
            print_results(f"Frontera resuelta para {args.nodo_id}", frontera)

            if frontera["exito"] and frontera["duplicados"]:
                print("  ⚠️ ALERTA: Hay duplicados en dispositivos_ids!")
                print(f"     Total: {frontera['total_count']}, Únicos: {frontera['unique_count']}\n")
        else:
            arbol = query_tree_structure(session, args.planta_id)
            print_results("D4: Estructura del árbol (primeros 50 nodos)", arbol[:50])

    finally:
        session.close()


if __name__ == "__main__":
    main()

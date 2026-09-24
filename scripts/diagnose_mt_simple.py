#!/usr/bin/env python3
"""Diagnóstico simple de bug de potencia MT - queries SQL puras."""

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Agregar raíz del proyecto al path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.infrastructure.settings.config import get_settings  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
_log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Diagnosticar bug de potencia MT")
    parser.add_argument("--planta-id", required=True, help="ID de planta (ej: durax)")
    parser.add_argument("--nodo-id", help="ID de nodo MT (ej: acometida-13200v)")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url)
    Session_factory = sessionmaker(bind=engine)
    session = Session_factory()

    try:
        print(f"\n{'=' * 70}")
        print(f"  Diagnóstico de bug potencia MT - Planta {args.planta_id}")
        print(f"{'=' * 70}\n")

        # D1+D2: Device IDs duplicados
        print("D1+D2: Buscando device_ids duplicados...\n")
        result = session.execute(
            text("""
            SELECT device_id, COUNT(*) as count, GROUP_CONCAT(id, ', ') as node_ids
            FROM unifilar_nodes
            WHERE planta_id = :planta_id AND device_id IS NOT NULL
            GROUP BY device_id
            HAVING COUNT(*) > 1
            ORDER BY count DESC;
        """),
            {"planta_id": args.planta_id},
        ).fetchall()

        if result:
            print("  ⚠️ DUPLICADOS DETECTADOS:\n")
            for row in result:
                print(f"    device_id: {row[0]}")
                print(f"      count: {row[1]}")
                print(f"      nodes: {row[2]}\n")
        else:
            print("  ✓ Sin duplicados detectados\n")

        # D2: Ciclos
        print(f"{'=' * 70}")
        print("D2: Buscando ciclos en el árbol...\n")
        result = session.execute(
            text("""
            WITH RECURSIVE ancestors AS (
                SELECT id, parent_id, 1 as depth
                FROM unifilar_nodes
                WHERE planta_id = :planta_id AND parent_id IS NOT NULL

                UNION ALL

                SELECT n.id, n.parent_id, a.depth + 1
                FROM unifilar_nodes n
                JOIN ancestors a ON n.id = a.parent_id
                WHERE n.planta_id = :planta_id AND a.depth < 100
            )
            SELECT n.id, n.parent_id
            FROM unifilar_nodes n
            WHERE n.planta_id = :planta_id
              AND n.parent_id IN (
                  SELECT id FROM ancestors
                  WHERE ancestors.parent_id = n.id
              );
        """),
            {"planta_id": args.planta_id},
        ).fetchall()

        if result:
            print("  ⚠️ CICLOS DETECTADOS:\n")
            for row in result:
                print(f"    {row[0]} -> {row[1]}\n")
        else:
            print("  ✓ Sin ciclos detectados\n")

        # D4: Árbol
        if args.nodo_id:
            print(f"{'=' * 70}")
            print(f"D4: Árbol desde nodo {args.nodo_id}...\n")
            result = session.execute(
                text("""
                WITH RECURSIVE tree AS (
                    SELECT id, parent_id, device_id, tipo, 0 as level
                    FROM unifilar_nodes
                    WHERE id = :nodo_id AND planta_id = :planta_id

                    UNION ALL

                    SELECT n.id, n.parent_id, n.device_id, n.tipo, t.level + 1
                    FROM unifilar_nodes n
                    JOIN tree t ON n.parent_id = t.id
                    WHERE n.planta_id = :planta_id AND t.level < 10
                )
                SELECT REPEAT('  ', level) || id as node_tree, device_id, tipo
                FROM tree
                ORDER BY level, parent_id, id;
            """),
                {"planta_id": args.planta_id, "nodo_id": args.nodo_id},
            ).fetchall()

            for row in result:
                print(f"  {row[0]:<40} device_id={row[1]:<15} tipo={row[2]}")
            print()

    finally:
        session.close()


if __name__ == "__main__":
    main()

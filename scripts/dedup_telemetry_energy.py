#!/usr/bin/env python3
"""scripts/dedup_telemetry_energy.py — WP2/D3: archiva filas duplicadas de telemetry_energy.

Contexto: acc y energyio pueden publicar el mismo (device_id, recorded_at) antes
de WP2. Se verificó contra datos reales (producción y el dump local) que NO hay
un criterio confiable para adivinar, a partir de los valores ya guardados, cuál
de las dos filas de un par vino de qué subtópico (ver docs/adr-001-no-redis-cache.md
y el plan de mejoras de base de datos, decisión D1/D3). Por eso este script no
intenta distinguir "la correcta": para cada grupo duplicado conserva la fila de
mayor `id` (la insertada más tarde) y archiva el resto — determinístico y auditable,
sin adivinar contenido.

D2 (nada almacenado se borra): "archivar" es un INSERT en telemetry_energy_archivo_dup
seguido de un DELETE en telemetry_energy, con commit por lote — el dato sigue
existiendo, solo cambia de tabla. Nunca se hace commit de un DELETE sin que el
INSERT del mismo lote haya quedado adentro de esa misma transacción.

Modo por defecto: --dry-run (solo reporta). Requiere --apply explícito para escribir.

Uso:
    python scripts/dedup_telemetry_energy.py                  # dry-run
    python scripts/dedup_telemetry_energy.py --apply           # aplica
    python scripts/dedup_telemetry_energy.py --apply --lote 5000
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.infrastructure.sqlalchemy.database import get_session_factory

TABLA_ARCHIVO = "telemetry_energy_archivo_dup"

_SQL_PERDEDORAS = (
    "SELECT t1.id FROM telemetry_energy t1"
    " WHERE EXISTS ("
    "   SELECT 1 FROM telemetry_energy t2"
    "   WHERE t2.device_id = t1.device_id AND t2.recorded_at = t1.recorded_at AND t2.id > t1.id"
    " )"
)


def _crear_tabla_archivo(db: Session) -> None:
    db.execute(text(f"CREATE TABLE IF NOT EXISTS {TABLA_ARCHIVO} LIKE telemetry_energy"))


def _contar_grupos_duplicados(db: Session) -> int:
    return db.execute(
        text(
            "SELECT COUNT(*) FROM ("
            "  SELECT device_id, recorded_at FROM telemetry_energy"
            "  GROUP BY device_id, recorded_at HAVING COUNT(*) > 1"
            ") t"
        )
    ).scalar_one()


def _contar_filas_a_archivar(db: Session) -> int:
    return db.execute(text(f"SELECT COUNT(*) FROM ({_SQL_PERDEDORAS}) t")).scalar_one()


def _archivar_lote(db: Session, lote: int) -> int:
    """Archiva hasta `lote` filas "perdedoras" (no el id máximo de su grupo).

    INSERT + DELETE antes del commit que hace el caller — ambos quedan en la
    misma transacción, o ninguno.
    """
    ids = db.execute(text(_SQL_PERDEDORAS + " LIMIT :lote"), {"lote": lote}).scalars().all()
    if not ids:
        return 0
    ids_sql = ",".join(str(int(i)) for i in ids)  # ids vienen de nuestra propia query (bigint), no de input externo
    db.execute(text(f"INSERT INTO {TABLA_ARCHIVO} SELECT * FROM telemetry_energy WHERE id IN ({ids_sql})"))
    db.execute(text(f"DELETE FROM telemetry_energy WHERE id IN ({ids_sql})"))
    return len(ids)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Aplica los cambios (default: dry-run).")
    parser.add_argument("--lote", type=int, default=5000, help="Filas por lote de archivado (default 5000).")
    args = parser.parse_args()

    session_factory = get_session_factory()
    db = session_factory()
    try:
        grupos = _contar_grupos_duplicados(db)
        a_archivar = _contar_filas_a_archivar(db)
        print(f"[i] Grupos (device_id, recorded_at) duplicados: {grupos}")
        print(f"[i] Filas a archivar (todas menos la de mayor id por grupo): {a_archivar}")

        if not args.apply:
            print("[i] Dry-run: no se escribió nada. Ejecutar con --apply para archivar de verdad.")
            return

        if a_archivar == 0:
            print("[+] Nada que archivar.")
            return

        _crear_tabla_archivo(db)
        db.commit()

        total = 0
        while True:
            movidas = _archivar_lote(db, args.lote)
            if movidas == 0:
                break
            db.commit()
            total += movidas
            print(f"[+] Archivadas {total}/{a_archivar}…")

        restantes = _contar_grupos_duplicados(db)
        print(f"[+] Listo. Total archivado: {total}. Grupos duplicados restantes: {restantes}")
        if restantes:
            print("[!] Quedan duplicados sin resolver — no se debe crear el índice único todavía.", file=sys.stderr)
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

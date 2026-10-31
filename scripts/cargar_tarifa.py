"""scripts/cargar_tarifa.py — Carga de una tarifa de capacidad verificada (datamaq#111, fase 1).

Modo simulación por defecto: muestra la fila que se insertaría y no escribe nada. Solo escribe con `--aplicar`.
Una corrección es otra fila con otra `--vigencia-desde`: nunca se edita una fila existente. El adaptador toma la
vigente más reciente (ver `RepositorioParametrosRegulatoriosSqlAlchemy`).

Aplicar en la base real es decisión del dueño y de DevOps. Los tests usan una base SQLite de prueba.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from src.infrastructure.sqlalchemy.models_parametros_regulatorios import TarifaCapacidadModel


def construir_fila(args: argparse.Namespace) -> dict[str, Any]:
    """Valida los argumentos y arma la fila de `tarifa_capacidad`. Sin I/O."""
    try:
        importe = Decimal(args.importe_capacidad)
        csc = Decimal(args.csc_kw)
    except InvalidOperation as exc:
        raise ValueError("importe y csc deben ser números decimales") from exc
    if importe <= 0 or csc <= 0:
        raise ValueError("importe y csc deben ser mayores que cero")
    if not args.fuente_archivo.strip() or not args.fuente_metodo.strip():
        raise ValueError("fuente_archivo y fuente_metodo son obligatorios")
    return {
        "distribuidora": args.distribuidora,
        "tarifa": args.tarifa,
        "periodo": args.periodo,
        "fuente_archivo": args.fuente_archivo,
        "fuente_metodo": args.fuente_metodo,
        "vigencia_desde": date.fromisoformat(args.vigencia_desde),
        "vigencia_hasta": None,
        "importe_capacidad_convenida_ars": importe,
        "csc_kw": csc,
    }


def aplicar(fila: dict[str, Any], session_factory: Callable[[], Session]) -> None:
    """Inserta la fila en una transacción. Solo se llama con `--aplicar`."""
    sesion = session_factory()
    try:
        sesion.add(TarifaCapacidadModel(**fila))
        sesion.commit()
    except Exception:
        sesion.rollback()
        raise
    finally:
        sesion.close()


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Carga una tarifa de capacidad verificada (simulación por defecto).")
    p.add_argument("--distribuidora", required=True)
    p.add_argument("--tarifa", required=True)
    p.add_argument("--periodo", required=True, help="AAAA-MM")
    p.add_argument("--importe-capacidad", required=True, help="importe de capacidad convenida, ARS")
    p.add_argument("--csc-kw", required=True)
    p.add_argument("--vigencia-desde", required=True, help="AAAA-MM-DD")
    p.add_argument("--fuente-archivo", required=True)
    p.add_argument("--fuente-metodo", required=True, help="p. ej. transcripcion_verificada")
    p.add_argument("--aplicar", action="store_true", help="escribe en la base; sin esta bandera solo simula")
    return p


def main(
    argv: Sequence[str] | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    try:
        fila = construir_fila(args)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    print(f"[SIMULACIÓN] fila a insertar en tarifa_capacidad: {fila}" if not args.aplicar else f"[APLICAR] {fila}")
    if not args.aplicar:
        return 0
    if session_factory is None:
        from src.infrastructure.sqlalchemy.database import get_session_factory

        session_factory = get_session_factory()
    aplicar(fila, session_factory)
    print("[OK] fila insertada")
    return 0


if __name__ == "__main__":
    sys.exit(main())

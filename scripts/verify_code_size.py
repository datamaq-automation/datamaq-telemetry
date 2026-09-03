#!/usr/bin/env python3
"""verify_code_size.py — Detección automática de archivos, clases y métodos sobredimensionados.

Audita el código en src/ contra umbrales de tamaño para preservar la modularidad,
legibilidad y el Principio de Responsabilidad Única (SRP) de Clean Architecture.

Mecanismo Ratchet / Baseline:
  Los componentes preexistentes que exceden los límites estándar están registrados con
  un techo máximo permitido ("baseline"). Ninguno de ellos puede crecer más allá de su
  techo, y cualquier nuevo componente que supere los umbrales estándar causa fallo inmediato.

Uso:
  python scripts/verify_code_size.py            # Verificación pre-push / CI
  python scripts/verify_code_size.py --report   # Reporte completo de auditoría
  python scripts/verify_code_size.py --strict   # Falla ante cualquier exceso (sin baseline)
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Umbrales estándar por defecto para nuevo código en src/
DEFAULT_MAX_FILE_LINES = 500
DEFAULT_MAX_CLASS_LINES = 300
DEFAULT_MAX_FUNC_LINES = 75

# Techos de deuda técnica preexistente (Ratchet).
# Ninguna entidad listada aquí puede exceder este valor de líneas.
# Al refactorizar y reducir una entidad, su techo debe ajustarse o removerse.
BASELINE_CEILINGS: dict[str, int] = {
    # Archivos
    "file:src/domain/telemetria/services.py": 1250,
    "file:src/infrastructure/sqlalchemy/mysql_repositories.py": 1200,
    "file:src/application/use_cases/ingestar_telemetria.py": 900,
    "file:src/domain/disponibilidad/services.py": 650,
    # Clases
    "class:src/domain/telemetria/services.py::AnalizadorCalidadEnergiaService": 900,
    "class:src/application/use_cases/ingestar_telemetria.py::IngestarTelemetriaUseCase": 820,
    "class:src/domain/disponibilidad/services.py::SegmentadorRegimenesService": 550,
    "class:src/infrastructure/sqlalchemy/mysql_repositories.py::MySQLTelemetriaRepository": 450,
    # Métodos y Funciones
    "func:src/application/use_cases/ingestar_telemetria.py::ejecutar": 550,
    "func:src/application/use_cases/ingestar_telemetria.py::_parse_fase": 150,
    "func:src/domain/telemetria/services.py::_agregar_grupo_lecturas": 140,
    "func:src/domain/telemetria/services.py::evaluar_alertas_distorsion_armonica": 120,
    "func:src/domain/telemetria/services.py::evaluar_alerta_tension": 115,
    "func:src/domain/telemetria/services.py::calcular_analitica_completa": 100,
    "func:src/infrastructure/fastapi/server.py::create_app": 95,
    "func:src/domain/telemetria/services.py::procesar_alerta": 90,
    "func:src/infrastructure/sqlalchemy/mysql_repositories.py::_instantanea_to_entity": 90,
    "func:src/application/use_cases/purgar_telemetria.py::ejecutar": 85,
}


@dataclass
class ItemMetric:
    kind: str  # "file", "class", "func"
    name: str
    rel_path: str
    lines: int
    lineno: int
    end_lineno: int


@dataclass
class AuditResult:
    files: list[ItemMetric]
    classes: list[ItemMetric]
    functions: list[ItemMetric]
    violations: list[str]
    warnings: list[str]


def analyze_codebase(
    src_dir: Path,
    max_file: int = DEFAULT_MAX_FILE_LINES,
    max_class: int = DEFAULT_MAX_CLASS_LINES,
    max_func: int = DEFAULT_MAX_FUNC_LINES,
    strict: bool = False,
) -> AuditResult:
    files_metrics: list[ItemMetric] = []
    classes_metrics: list[ItemMetric] = []
    funcs_metrics: list[ItemMetric] = []
    violations: list[str] = []
    warnings: list[str] = []

    for root, _, files in os.walk(src_dir):
        for file in sorted(files):
            if not file.endswith(".py"):
                continue

            full_path = Path(root) / file
            rel_path = full_path.relative_to(src_dir.parent).as_posix()

            try:
                content = full_path.read_text(encoding="utf-8")
            except Exception as e:
                warnings.append(f"No se pudo leer {rel_path}: {e}")
                continue

            lines = content.splitlines()
            file_len = len(lines)
            f_metric = ItemMetric(
                kind="file",
                name=rel_path,
                rel_path=rel_path,
                lines=file_len,
                lineno=1,
                end_lineno=file_len,
            )
            files_metrics.append(f_metric)

            # Verificar límite de archivo
            key_file = f"file:{rel_path}"
            if file_len > max_file:
                if not strict and key_file in BASELINE_CEILINGS:
                    ceiling = BASELINE_CEILINGS[key_file]
                    if file_len > ceiling:
                        violations.append(
                            f"[ARCHIVO EXCEDIDO] {rel_path}: {file_len} líneas (superó el techo baseline de {ceiling})"
                        )
                    else:
                        warnings.append(f"[BASELINE DEUDA] Archivo {rel_path}: {file_len} líneas (techo: {ceiling})")
                else:
                    violations.append(f"[ARCHIVO EXCEDIDO] {rel_path}: {file_len} líneas (límite: {max_file})")

            try:
                tree = ast.parse(content, filename=str(full_path))
            except Exception as e:
                warnings.append(f"Error parseando AST de {rel_path}: {e}")
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    c_len = (node.end_lineno - node.lineno + 1) if getattr(node, "end_lineno", None) else 0
                    c_metric = ItemMetric(
                        kind="class",
                        name=node.name,
                        rel_path=rel_path,
                        lines=c_len,
                        lineno=node.lineno,
                        end_lineno=getattr(node, "end_lineno", node.lineno),
                    )
                    classes_metrics.append(c_metric)

                    key_class = f"class:{rel_path}::{node.name}"
                    if c_len > max_class:
                        if not strict and key_class in BASELINE_CEILINGS:
                            ceiling = BASELINE_CEILINGS[key_class]
                            if c_len > ceiling:
                                violations.append(
                                    f"[CLASE EXCEDIDA] {rel_path}::{node.name} (L{node.lineno}): "
                                    f"{c_len} líneas (superó el techo baseline de {ceiling})"
                                )
                            else:
                                warnings.append(
                                    f"[BASELINE DEUDA] Clase {rel_path}::{node.name}: {c_len} líneas (techo: {ceiling})"
                                )
                        else:
                            violations.append(
                                f"[CLASE EXCEDIDA] {rel_path}::{node.name} (L{node.lineno}): "
                                f"{c_len} líneas (límite: {max_class})"
                            )

                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    f_len = (node.end_lineno - node.lineno + 1) if getattr(node, "end_lineno", None) else 0
                    fn_metric = ItemMetric(
                        kind="func",
                        name=node.name,
                        rel_path=rel_path,
                        lines=f_len,
                        lineno=node.lineno,
                        end_lineno=getattr(node, "end_lineno", node.lineno),
                    )
                    funcs_metrics.append(fn_metric)

                    key_func = f"func:{rel_path}::{node.name}"
                    if f_len > max_func:
                        if not strict and key_func in BASELINE_CEILINGS:
                            ceiling = BASELINE_CEILINGS[key_func]
                            if f_len > ceiling:
                                violations.append(
                                    f"[MÉTODO EXCEDIDO] {rel_path}::{node.name} (L{node.lineno}): "
                                    f"{f_len} líneas (superó el techo baseline de {ceiling})"
                                )
                            else:
                                warnings.append(
                                    f"[BASELINE DEUDA] Método {rel_path}::{node.name}: "
                                    f"{f_len} líneas (techo: {ceiling})"
                                )
                        else:
                            violations.append(
                                f"[MÉTODO EXCEDIDO] {rel_path}::{node.name} (L{node.lineno}): "
                                f"{f_len} líneas (límite: {max_func})"
                            )

    return AuditResult(
        files=files_metrics,
        classes=classes_metrics,
        functions=funcs_metrics,
        violations=violations,
        warnings=warnings,
    )


def print_report(result: AuditResult, top_n: int = 10) -> None:
    print("\n" + "=" * 78)
    print(" 📊 REPORTE DE AUDITORÍA DE TAMAÑO DE CÓDIGO (src/)")
    print("=" * 78)

    print(f"\n📂 TOP {top_n} ARCHIVOS MÁS EXTENSOS:")
    print(f"{'Líneas':>7} | {'Archivo'}")
    print("-" * 78)
    for m in sorted(result.files, key=lambda x: x.lines, reverse=True)[:top_n]:
        print(f"{m.lines:7d} | {m.rel_path}")

    print(f"\n🏛️  TOP {top_n} CLASES MÁS EXTENSAS:")
    print(f"{'Líneas':>7} | {'Clase'} ({'Ubicación'})")
    print("-" * 78)
    for m in sorted(result.classes, key=lambda x: x.lines, reverse=True)[:top_n]:
        print(f"{m.lines:7d} | {m.name} ({m.rel_path}:{m.lineno})")

    print(f"\n⚙️  TOP {top_n} MÉTODOS/FUNCIONES MÁS EXTENSOS:")
    print(f"{'Líneas':>7} | {'Función/Método'} ({'Ubicación'})")
    print("-" * 78)
    for m in sorted(result.functions, key=lambda x: x.lines, reverse=True)[:top_n]:
        print(f"{m.lines:7d} | {m.name} ({m.rel_path}:{m.lineno})")

    print("\n" + "=" * 78)
    print(f"Total archivos analizados : {len(result.files)}")
    print(f"Total clases analizadas   : {len(result.classes)}")
    print(f"Total funciones/métodos   : {len(result.functions)}")
    print(f"Deuda bajo baseline       : {len(result.warnings)}")
    print(f"Violaciones bloqueantes   : {len(result.violations)}")
    print("=" * 78 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verifica que archivos, clases y métodos no excedan los límites permitidos."
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Imprime el reporte detallado con las entidades más extensas.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Modo estricto: falla ante cualquier entidad que supere los límites (ignora baseline).",
    )
    parser.add_argument(
        "--max-file-lines",
        type=int,
        default=DEFAULT_MAX_FILE_LINES,
        help=f"Límite máximo de líneas por archivo (default: {DEFAULT_MAX_FILE_LINES})",
    )
    parser.add_argument(
        "--max-class-lines",
        type=int,
        default=DEFAULT_MAX_CLASS_LINES,
        help=f"Límite máximo de líneas por clase (default: {DEFAULT_MAX_CLASS_LINES})",
    )
    parser.add_argument(
        "--max-func-lines",
        type=int,
        default=DEFAULT_MAX_FUNC_LINES,
        help=f"Límite máximo de líneas por función/método (default: {DEFAULT_MAX_FUNC_LINES})",
    )

    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parent.parent
    src_dir = root_dir / "src"

    result = analyze_codebase(
        src_dir=src_dir,
        max_file=args.max_file_lines,
        max_class=args.max_class_lines,
        max_func=args.max_func_lines,
        strict=args.strict,
    )

    if args.report:
        print_report(result)

    if result.violations:
        print("\n❌ [FAIL] Se detectaron violaciones de tamaño de código:")
        for v in result.violations:
            print(f"   • {v}")
        print("\nReduzca o refactorice los componentes para cumplir los límites arquitectónicos.")
        sys.exit(1)
    else:
        print("[PASS] Ningún archivo, clase o método excede los límites de tamaño permitidos.")
        sys.exit(0)


if __name__ == "__main__":
    main()

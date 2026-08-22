"""test_architecture.py — El Guantelete de Restricciones Extremas (Clean Architecture & DDD).

Inspirado en la filosofía de Robert C. Martin ("Uncle Bob") sobre el desarrollo asistido por agentes IA:
"Rodear a los agentes de restricciones extremas para tener máxima confianza en el código producido."

Este archivo ejecuta un análisis estático exhaustivo mediante el Árbol de Sintaxis Abstracta (AST)
de Python y la librería estándar, sin dependencias externas obligatorias.

Batería de Pruebas ("The Constraint Gauntlet"):
  1. test_init_files_must_be_empty:
     - El 100% de los archivos __init__.py en src/ y tests/ deben tener exactamente 0 bytes.
  2. test_clean_architecture_compliance:
     - Domain: No importa application, adapters, infrastructure, fastapi ni ORMs/drivers de persistencia.
     - Application: No importa adapters, infrastructure, fastapi ni ORMs.
     - Adapters: No importa infrastructure ni fastapi/starlette.
     - Infrastructure (Routers): No importan ORMs directamente (controladores delgados).
  3. test_no_relative_imports:
     - Prohíbe terminantemente imports relativos ('from . import' / 'from .. import'). Solo 'from src...'.
  4. test_all_functions_have_type_annotations:
     - Exige que todas las funciones y métodos en domain y application especifiquen Type Hints en parámetros y retorno.
  5. test_no_hardcoded_secrets:
     - Detecta credenciales, passwords, tokens JWT o connection strings quemadas en código fuente.

Uso:
  - Con Pytest:  pytest tests/test_architecture.py -v
  - Como Script: python3 tests/test_architecture.py
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple


def find_project_root(start_path: Optional[Path] = None) -> Path:
    """Encuentra la raíz del proyecto buscando el directorio 'src' hacia arriba."""
    current = (start_path or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / "src").is_dir():
            return parent
    return Path.cwd().resolve()


def parse_ast_safely(file_path: Path) -> Optional[ast.AST]:
    """Parsea un archivo Python a AST de forma segura."""
    try:
        content = file_path.read_text(encoding="utf-8")
        return ast.parse(content, filename=str(file_path))
    except Exception as e:
        print(f"[ERROR] No se pudo parsear {file_path}: {e}", file=sys.stderr)
        return None


def extract_imports(tree: ast.AST) -> List[Tuple[str, int, bool]]:
    """Extrae todos los módulos importados en un árbol AST.

    Retorna lista de tuplas: (nombre_modulo, linea, es_relativo)
    """
    imports: List[Tuple[str, int, bool]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    imports.append((alias.name, node.lineno, False))
        elif isinstance(node, ast.ImportFrom):
            is_relative = node.level is not None and node.level > 0
            module_name = node.module or ""
            imports.append((module_name, node.lineno, is_relative))
    return imports


# ==============================================================================
# 1. Verificación de Archivos __init__.py (0 bytes)
# ==============================================================================

def verify_init_files_empty(root_dir: Optional[Path] = None) -> List[str]:
    """Verifica que todos los archivos __init__.py en src/ y tests/ tengan exactamente 0 bytes."""
    root = root_dir or find_project_root()
    errors: List[str] = []

    for target_dir in [root / "src", root / "tests"]:
        if not target_dir.exists() or not target_dir.is_dir():
            continue

        for current_root, _, files in os.walk(target_dir):
            for file in files:
                if file == "__init__.py":
                    full_path = Path(current_root) / file
                    size = full_path.stat().st_size
                    if size != 0:
                        rel_path = full_path.relative_to(root).as_posix()
                        errors.append(
                            f"[INIT NO VACÍO] '{rel_path}' tiene {size} bytes. Debe tener exactamente 0 bytes."
                        )

    return errors


# ==============================================================================
# 2. Verificación de Reglas de Capas Clean Architecture
# ==============================================================================

def verify_architecture_layers(root_dir: Optional[Path] = None) -> List[str]:
    """Verifica el cumplimiento de la regla de dependencias entre capas."""
    root = root_dir or find_project_root()
    src_dir = root / "src"
    errors: List[str] = []

    if not src_dir.exists():
        return [f"[ERROR] No se encontró el directorio de código fuente: {src_dir}"]

    domain_forbidden = (
        "fastapi", "starlette", "sqlalchemy", "sqlmodel", "tortoise",
        "httpx", "requests", "aiohttp", "pymysql", "psycopg", "psycopg2",
        "asyncpg", "paho", "aiokafka", "kafka", "redis", "celery",
        "src.application", "src.adapters", "src.infrastructure", "src.main",
    )

    application_forbidden = (
        "fastapi", "starlette", "sqlalchemy", "sqlmodel", "tortoise",
        "pymysql", "psycopg", "psycopg2", "asyncpg", "paho", "aiokafka",
        "kafka", "redis", "src.adapters", "src.infrastructure", "src.main",
    )

    adapters_forbidden = (
        "fastapi", "starlette", "src.infrastructure", "src.main",
    )

    for current_root, _, files in os.walk(src_dir):
        for file in files:
            if not file.endswith(".py") or file == "__init__.py":
                continue

            full_path = Path(current_root) / file
            rel_path = full_path.relative_to(root).as_posix()
            tree = parse_ast_safely(full_path)
            if not tree:
                continue

            imports = extract_imports(tree)
            for module_name, lineno, _ in imports:
                if "src/domain" in rel_path and any(module_name.startswith(pkg) for pkg in domain_forbidden):
                    errors.append(f"[DOMINIO VIOLADO] {rel_path}:{lineno} importa módulo prohibido '{module_name}'.")

                elif "src/application" in rel_path and any(module_name.startswith(pkg) for pkg in application_forbidden):
                    errors.append(f"[APLICACIÓN VIOLADA] {rel_path}:{lineno} importa módulo prohibido '{module_name}'.")

                elif "src/adapters" in rel_path and any(module_name.startswith(pkg) for pkg in adapters_forbidden):
                    errors.append(f"[ADAPTADORES VIOLADO] {rel_path}:{lineno} importa módulo prohibido '{module_name}'.")

                elif ("src/infrastructure/fastapi/routers" in rel_path or "src/infrastructure/fastapi/routes" in rel_path):
                    if any(module_name.startswith(pkg) for pkg in ("sqlalchemy", "sqlmodel")):
                        errors.append(
                            f"[THIN CONTROLLER VIOLADO] {rel_path}:{lineno} importa '{module_name}' directamente (debe delegar en use cases)."
                        )

    return errors


# ==============================================================================
# 3. Verificación de Imports Absolutos
# ==============================================================================

def verify_no_relative_imports(root_dir: Optional[Path] = None) -> List[str]:
    """Verifica que ningún módulo en src/ contenga imports relativos."""
    root = root_dir or find_project_root()
    src_dir = root / "src"
    errors: List[str] = []

    if not src_dir.exists():
        return []

    for current_root, _, files in os.walk(src_dir):
        for file in files:
            if not file.endswith(".py") or file == "__init__.py":
                continue

            full_path = Path(current_root) / file
            rel_path = full_path.relative_to(root).as_posix()
            tree = parse_ast_safely(full_path)
            if not tree:
                continue

            for module_name, lineno, is_relative in extract_imports(tree):
                if is_relative:
                    errors.append(
                        f"[IMPORT RELATIVO] {rel_path}:{lineno} usa import relativo '{module_name}'. Use 'from src...'."
                    )

    return errors


# ==============================================================================
# 4. Verificación de Tipado Estricto en Funciones de Dominio y Aplicación
# ==============================================================================

def verify_type_annotations(root_dir: Optional[Path] = None) -> List[str]:
    """Verifica que todas las funciones en domain y application tengan Type Hints explícitos."""
    root = root_dir or find_project_root()
    src_dir = root / "src"
    errors: List[str] = []

    if not src_dir.exists():
        return []

    target_layers = [src_dir / "domain", src_dir / "application"]

    for layer_dir in target_layers:
        if not layer_dir.exists():
            continue

        for current_root, _, files in os.walk(layer_dir):
            for file in files:
                if not file.endswith(".py") or file == "__init__.py":
                    continue

                full_path = Path(current_root) / file
                rel_path = full_path.relative_to(root).as_posix()
                tree = parse_ast_safely(full_path)
                if not tree:
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        func_name = node.name
                        # Ignorar métodos mágicos especiales excepto __init__
                        if func_name.startswith("__") and func_name.endswith("__") and func_name != "__init__":
                            continue

                        # 1. Verificar retorno tipado (excepto __init__)
                        if func_name != "__init__" and node.returns is None:
                            errors.append(
                                f"[FALTA TYPE HINT RETORNO] {rel_path}:{node.lineno} la función '{func_name}' no especifica tipo de retorno ('-> Type')."
                            )

                        # 2. Verificar argumentos tipados (excepto self y cls)
                        for arg in node.args.args:
                            if arg.arg in ("self", "cls"):
                                continue
                            if arg.annotation is None:
                                errors.append(
                                    f"[FALTA TYPE HINT PARÁMETRO] {rel_path}:{node.lineno} el parámetro '{arg.arg}' en '{func_name}' no tiene type annotation."
                                )

    return errors


# ==============================================================================
# 5. Verificación de Secretos y Parámetros Críticos Hardcodeados
# ==============================================================================

def verify_no_hardcoded_secrets(root_dir: Optional[Path] = None) -> List[str]:
    """Detecta contraseñas, connection strings o tokens secretos quemados en el código."""
    root = root_dir or find_project_root()
    src_dir = root / "src"
    errors: List[str] = []

    if not src_dir.exists():
        return []

    suspicious_patterns = [
        (re.compile(r"""(?:password|secret_key|api_key|token)\s*=\s*['"][a-zA-Z0-9_\-]{8,}['"]""", re.IGNORECASE), "Posible credencial/token quemado en código"),
        (re.compile(r"""(?:postgres|mysql|mariadb|mongodb):\/\/[^:]+:[^@]+@""", re.IGNORECASE), "Connection string con contraseña en código fuente"),
        (re.compile(r"""['"]eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}""", re.IGNORECASE), "Token JWT quemado en código fuente"),
    ]

    for current_root, _, files in os.walk(src_dir):
        for file in files:
            if not file.endswith(".py"):
                continue

            full_path = Path(current_root) / file
            rel_path = full_path.relative_to(root).as_posix()
            
            # Excluir archivos de configuración donde se definan defaults de desarrollo seguros
            if "src/infrastructure/settings/config.py" in rel_path:
                continue

            try:
                lines = full_path.read_text(encoding="utf-8").splitlines()
                for lineno, line in enumerate(lines, start=1):
                    # Ignorar comentarios
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    for pattern, desc in suspicious_patterns:
                        if pattern.search(line):
                            errors.append(f"[SECRETO HARDCODEADO] {rel_path}:{lineno} {desc}. Centralice en Settings.")
            except Exception:
                pass

    return errors


# ==============================================================================
# Suite de Pruebas Pytest ("The Constraint Gauntlet")
# ==============================================================================

def test_init_files_must_be_empty():
    """Restricción 1: El 100% de los archivos __init__.py deben tener exactamente 0 bytes."""
    errors = verify_init_files_empty()
    assert not errors, (
        f"\n❌ Se detectaron {len(errors)} archivos __init__.py no vacíos:\n\n"
        + "\n".join(f"  • {err}" for err in errors)
    )


def test_clean_architecture_compliance():
    """Restricción 2: Las dependencias entre capas deben respetar Clean Architecture y DDD."""
    errors = verify_architecture_layers()
    assert not errors, (
        f"\n❌ Se detectaron {len(errors)} violaciones de Clean Architecture:\n\n"
        + "\n".join(f"  • {err}" for err in errors)
    )


def test_no_relative_imports():
    """Restricción 3: Todos los imports en src/ deben ser absolutos ('from src...')."""
    errors = verify_no_relative_imports()
    assert not errors, (
        f"\n❌ Se detectaron {len(errors)} imports relativos prohibidos:\n\n"
        + "\n".join(f"  • {err}" for err in errors)
    )


def test_all_functions_have_type_annotations():
    """Restricción 4: 100% de funciones en domain y application deben tener Type Hints."""
    errors = verify_type_annotations()
    assert not errors, (
        f"\n❌ Se detectaron {len(errors)} funciones sin tipado estricto:\n\n"
        + "\n".join(f"  • {err}" for err in errors)
    )


def test_no_hardcoded_secrets():
    """Restricción 5: Prohibido hardcodear contraseñas, tokens y connection strings en código."""
    errors = verify_no_hardcoded_secrets()
    assert not errors, (
        f"\n❌ Se detectaron {len(errors)} secretos hardcodeados:\n\n"
        + "\n".join(f"  • {err}" for err in errors)
    )


# ==============================================================================
# CLI Runner Independiente
# ==============================================================================

def main() -> None:
    """Ejecuta el Guantelete Completo de Restricciones desde línea de comandos."""
    print("=" * 70)
    print("🛡️  EJECUTANDO EL GUANTELETE DE RESTRICCIONES (Uncle Bob Paradigm)")
    print("=" * 70)

    suites = [
        ("1. Archivos __init__.py (0 bytes)", verify_init_files_empty()),
        ("2. Dependencias de Capas (Clean Architecture)", verify_architecture_layers()),
        ("3. Imports Absolutos (Prohibidos relativos)", verify_no_relative_imports()),
        ("4. Tipado Estricto (Domain & Application)", verify_type_annotations()),
        ("5. Seguridad & Secretos (Cero hardcoded)", verify_no_hardcoded_secrets()),
    ]

    total_errors: List[str] = []

    for name, errors in suites:
        if errors:
            print(f"\n❌ [FALLÓ] {name}: {len(errors)} violaciones")
            for err in errors:
                print(f"   • {err}")
            total_errors.extend(errors)
        else:
            print(f"✅ [APROBADO] {name}")

    print("\n" + "=" * 70)
    if total_errors:
        print(f"💥 RESULTADO FINAL: {len(total_errors)} violaciones detectadas.")
        print("Los agentes o desarrolladores deben corregir el código para superar el guantelete.")
        print("=" * 70)
        sys.exit(1)
    else:
        print("🎉 RESULTADO FINAL: 100% de las restricciones arquitectónicas fueron superadas con éxito.")
        print("=" * 70)
        sys.exit(0)


if __name__ == "__main__":
    main()

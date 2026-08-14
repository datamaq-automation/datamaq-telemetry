import ast
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")


def get_all_imports(file_path: str):
    with open(file_path, encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=file_path)
        except Exception as e:
            print(f"[ERROR] No se pudo parsear {file_path}: {e}")
            return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def verify_architecture():
    errors = []

    for root, _, files in os.walk(SRC_DIR):
        for file in files:
            if not file.endswith(".py"):
                continue

            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, ROOT_DIR)
            imports = get_all_imports(full_path)

            # 1. Regla de Dominio: Solo stdlib
            if "src/domain" in rel_path:
                forbidden = ("fastapi", "sqlalchemy", "pydantic", "paho", "starlette", "pymysql")
                for imp in imports:
                    if (
                        any(imp.startswith(f) for f in forbidden)
                        or "src.application" in imp
                        or "src.adapters" in imp
                        or "src.infrastructure" in imp
                    ):
                        errors.append(f"[DOMINIO VIOLADO] {rel_path} importa módulo prohibido '{imp}'")

            # 2. Regla de Aplicación: Solo domain + pydantic
            elif "src/application" in rel_path:
                forbidden = (
                    "fastapi",
                    "sqlalchemy",
                    "paho",
                    "starlette",
                    "pymysql",
                    "src.adapters",
                    "src.infrastructure",
                )
                for imp in imports:
                    if any(imp.startswith(f) for f in forbidden):
                        errors.append(f"[APLICACIÓN VIOLADA] {rel_path} importa módulo prohibido '{imp}'")

            # 3. Regla de Adaptadores: No importa infrastructure ni fastapi
            elif "src/adapters" in rel_path:
                forbidden = ("fastapi", "starlette", "src.infrastructure")
                for imp in imports:
                    if any(imp.startswith(f) for f in forbidden):
                        errors.append(f"[ADAPTADORES VIOLADO] {rel_path} importa módulo prohibido '{imp}'")

    if errors:
        print("\n".join(errors))
        print(f"\n[FAIL] Se encontraron {len(errors)} violaciones de arquitectura.")
        sys.exit(1)
    else:
        print("[PASS] Todas las reglas de Clean Architecture & DDD fueron respetadas.")


if __name__ == "__main__":
    verify_architecture()

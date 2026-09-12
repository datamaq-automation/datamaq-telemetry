"""tests/test_god_components.py — Auditoría de Componentes Dios (Monolitos) en src/.

Detecta, mediante análisis estático AST ($0 tokens), archivos/clases/funciones que concentran
demasiada responsabilidad y son candidatos a refactor por Single Responsibility Principle:

  - GOD_FILE: archivo .py con más de FILE_LOC_THRESHOLD líneas de código (sin contar blancos/comentarios).
  - GOD_CLASS: clase con más de CLASS_METHODS_THRESHOLD métodos definidos.
  - GOD_FUNCTION: función/método con más de FUNCTION_LOC_THRESHOLD líneas de cuerpo.

Uso:
  - Con Pytest:  pytest tests/test_god_components.py -v
  - Como Script: python3 tests/test_god_components.py [--strict] [--json]

`--strict` hace que cualquier hallazgo produzca exit code 1 (para CI).
Sin `--strict`, el script informa hallazgos pero no falla (uso exploratorio humano).
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

FILE_LOC_THRESHOLD = 400
CLASS_METHODS_THRESHOLD = 20
FUNCTION_LOC_THRESHOLD = 60


@dataclass(frozen=True)
class Finding:
    kind: str
    path: str
    name: str
    line: int
    metric: int
    threshold: int


def find_project_root(start_path: Path | None = None) -> Path:
    """Encuentra la raíz del proyecto buscando el directorio 'src' hacia arriba."""
    current = (start_path or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / "src").is_dir():
            return parent
    return Path.cwd().resolve()


def _code_loc(text: str) -> int:
    """Cuenta líneas no vacías y no puramente comentario."""
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


def _function_body_loc(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    if not node.body:
        return 0
    start = node.body[0].lineno
    end = max(
        getattr(n, "end_lineno", n.lineno)
        for stmt in node.body
        for n in ast.walk(stmt)
        if hasattr(n, "lineno")
    )
    return end - start + 1


def scan_file(path: Path, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    rel_path = path.relative_to(root).as_posix()

    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
    except Exception:
        return findings

    file_loc = _code_loc(text)
    if file_loc > FILE_LOC_THRESHOLD:
        findings.append(Finding("GOD_FILE", rel_path, path.name, 1, file_loc, FILE_LOC_THRESHOLD))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            method_count = sum(1 for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
            if method_count > CLASS_METHODS_THRESHOLD:
                findings.append(
                    Finding("GOD_CLASS", rel_path, node.name, node.lineno, method_count, CLASS_METHODS_THRESHOLD)
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            loc = _function_body_loc(node)
            if loc > FUNCTION_LOC_THRESHOLD:
                findings.append(
                    Finding("GOD_FUNCTION", rel_path, node.name, node.lineno, loc, FUNCTION_LOC_THRESHOLD)
                )

    return findings


def scan_src(root_dir: Path | None = None) -> list[Finding]:
    root = root_dir or find_project_root()
    src_dir = root / "src"
    if not src_dir.exists():
        return []

    findings: list[Finding] = []
    for path in sorted(src_dir.rglob("*.py")):
        if path.name == "__init__.py" or "__pycache__" in path.parts:
            continue
        findings.extend(scan_file(path, root))
    return findings


def format_findings(findings: list[Finding]) -> str:
    lines = []
    for f in findings:
        lines.append(f"  • [{f.kind}] {f.path}:{f.line} '{f.name}' ({f.metric} > {f.threshold})")
    return "\n".join(lines)


# ==============================================================================
# Suite de Pruebas Pytest (informativa, no bloqueante por defecto)
# ==============================================================================


def test_no_god_components_report():
    """Reporta God Components detectados en src/ (no falla el build por defecto, ver --strict en CLI)."""
    findings = scan_src()
    if findings:
        print(f"\n⚠️  {len(findings)} candidatos a Componente Dios detectados:\n{format_findings(findings)}")


# ==============================================================================
# CLI Runner Independiente
# ==============================================================================


def main() -> None:
    strict = "--strict" in sys.argv
    as_json = "--json" in sys.argv

    findings = scan_src()

    if as_json:
        print(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=2))
    else:
        print("=" * 70)
        print("🔍  AUDITORÍA DE COMPONENTES DIOS (God Components)")
        print("=" * 70)
        if findings:
            print(f"\n⚠️  {len(findings)} hallazgos:\n{format_findings(findings)}")
        else:
            print("\n✅ No se detectaron Componentes Dios en src/.")
        print("=" * 70)

    if strict and findings:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

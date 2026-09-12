"""tests/test_clean_design.py — Detección Determinística de Código Muerto y Sobreingeniería.

Complementa el Guantelete (tests/test_architecture.py) y la Auditoría de Componentes Dios
(tests/test_god_components.py) analizando el AST local ($0 tokens) para evitar sesgos típicos
de agentes IA: código huérfano, interfaces innecesarias (YAGNI), delegación sin valor,
herencia profunda y símbolos privados sin uso.

Baterías:
  1. UNREACHABLE_FILE: archivo .py en src/ no alcanzable desde src/main.py ni desde tests/.
  2. GHOST_INTERFACE: Protocol/ABC con una sola implementación concreta en src/ y 0 mocks en tests/.
  3. MIDDLE_MAN_METHOD: método que solo delega argumentos idénticos a otro objeto sin lógica propia.
  4. DEEP_INHERITANCE: árbol de herencia con profundidad > 2 (DIT > 2).
  5. ORPHAN_PRIVATE_SYMBOL: función/clase/método privado (`_nombre`) declarado y nunca referenciado
     en su propio módulo.
  6. SPECULATIVE_MICRO_FILE: archivo .py con menos de 10 líneas de código, sin justificación aparente.

Uso:
  - Con Pytest:  pytest tests/test_clean_design.py -v
  - Como Script: python3 tests/test_clean_design.py [--strict] [--json]

`--strict` hace que cualquier hallazgo produzca exit code 1 (para CI).
Sin `--strict`, el script informa hallazgos pero no falla (uso exploratorio humano).
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

MICRO_FILE_LOC_THRESHOLD = 10
MAX_INHERITANCE_DEPTH = 2


@dataclass(frozen=True)
class Finding:
    kind: str
    path: str
    name: str
    line: int
    detail: str


def find_project_root(start_path: Path | None = None) -> Path:
    """Encuentra la raíz del proyecto buscando el directorio 'src' hacia arriba."""
    current = (start_path or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / "src").is_dir():
            return parent
    return Path.cwd().resolve()


def _iter_py_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        p for p in directory.rglob("*.py") if p.name != "__init__.py" and "__pycache__" not in p.parts
    )


def _module_name(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    return ".".join(rel.parts)


def _parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception:
        return None


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _matches_module(imported: str, candidate: str) -> bool:
    return imported == candidate or imported.startswith(candidate + ".")


# ------------------------------------------------------------------------------
# 1. UNREACHABLE_FILE
# ------------------------------------------------------------------------------


def check_unreachable_files(root: Path) -> list[Finding]:
    src_dir = root / "src"
    tests_dir = root / "tests"
    all_src_files = _iter_py_files(src_dir)
    if not all_src_files:
        return []

    module_by_name = {_module_name(p, root): p for p in all_src_files}
    entry_points = [p for p in all_src_files if p.name == "main.py"]

    all_scanner_files = all_src_files + _iter_py_files(tests_dir)
    reachable: set[str] = set()
    queue: list[str] = [_module_name(p, root) for p in entry_points]

    # Todo archivo referenciado desde cualquier import (src o tests) se considera alcanzado.
    for scanner_path in all_scanner_files:
        tree = _parse(scanner_path)
        if tree is None:
            continue
        for imported in _imported_modules(tree):
            for name in module_by_name:
                if _matches_module(imported, name):
                    queue.append(name)

    reachable.update(queue)
    reachable.update(_module_name(p, root) for p in entry_points)

    findings: list[Finding] = []
    for name, path in module_by_name.items():
        if name in reachable:
            continue
        rel_path = path.relative_to(root).as_posix()
        findings.append(Finding("UNREACHABLE_FILE", rel_path, path.name, 1, "No referenciado desde main.py ni tests/"))
    return findings


# ------------------------------------------------------------------------------
# 2. GHOST_INTERFACE
# ------------------------------------------------------------------------------


def check_ghost_interfaces(root: Path) -> list[Finding]:
    src_dir = root / "src"
    tests_dir = root / "tests"
    findings: list[Finding] = []

    interfaces: dict[str, tuple[Path, int]] = {}
    for path in _iter_py_files(src_dir):
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = {b.id for b in node.bases if isinstance(b, ast.Name)}
            base_attrs = {b.attr for b in node.bases if isinstance(b, ast.Attribute)}
            if "Protocol" in base_names or "ABC" in base_names or "Protocol" in base_attrs:
                interfaces[node.name] = (path, node.lineno)

    if not interfaces:
        return []

    concrete_impl_count: dict[str, int] = dict.fromkeys(interfaces, 0)
    for path in _iter_py_files(src_dir):
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = {b.id for b in node.bases if isinstance(b, ast.Name)}
            for iface in base_names & interfaces.keys():
                if node.name != iface:
                    concrete_impl_count[iface] += 1

    mock_usage: dict[str, int] = dict.fromkeys(interfaces, 0)
    for path in _iter_py_files(tests_dir):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for iface in interfaces:
            if iface in text:
                mock_usage[iface] += 1

    for iface, (path, lineno) in interfaces.items():
        if concrete_impl_count[iface] <= 1 and mock_usage[iface] == 0:
            rel_path = path.relative_to(root).as_posix()
            findings.append(
                Finding(
                    "GHOST_INTERFACE",
                    rel_path,
                    iface,
                    lineno,
                    f"{concrete_impl_count[iface]} implementación(es) concreta(s) y 0 mocks en tests/",
                )
            )
    return findings


# ------------------------------------------------------------------------------
# 3. MIDDLE_MAN_METHOD
# ------------------------------------------------------------------------------


def _is_pure_delegation(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = [n for n in func.body if not isinstance(n, ast.Expr) or not isinstance(n.value, ast.Constant)]
    if len(body) != 1:
        return False

    stmt = body[0]
    call: ast.Call | None = None
    if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call):
        call = stmt.value
    elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        call = stmt.value
    if call is None:
        return False

    own_args = [a.arg for a in func.args.args if a.arg != "self"]
    call_arg_names: list[str] = []
    for arg in call.args:
        if isinstance(arg, ast.Name):
            call_arg_names.append(arg.id)
        else:
            return False

    return own_args == call_arg_names and len(own_args) > 0


def check_middle_man_methods(root: Path) -> list[Finding]:
    src_dir = root / "src"
    findings: list[Finding] = []

    for path in _iter_py_files(src_dir):
        tree = _parse(path)
        if tree is None:
            continue
        rel_path = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_pure_delegation(item):
                        findings.append(
                            Finding(
                                "MIDDLE_MAN_METHOD",
                                rel_path,
                                f"{node.name}.{item.name}",
                                item.lineno,
                                "Delega argumentos idénticos sin lógica propia",
                            )
                        )
    return findings


# ------------------------------------------------------------------------------
# 4. DEEP_INHERITANCE
# ------------------------------------------------------------------------------


def check_deep_inheritance(root: Path) -> list[Finding]:
    src_dir = root / "src"
    class_bases: dict[str, list[str]] = {}
    class_location: dict[str, tuple[Path, int]] = {}

    for path in _iter_py_files(src_dir):
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
                class_bases[node.name] = bases
                class_location[node.name] = (path, node.lineno)

    def depth(name: str, seen: frozenset[str] = frozenset()) -> int:
        if name in seen or name not in class_bases:
            return 0
        bases = class_bases[name]
        if not bases:
            return 0
        return 1 + max((depth(b, seen | {name}) for b in bases), default=0)

    findings: list[Finding] = []
    for name in class_bases:
        d = depth(name)
        if d > MAX_INHERITANCE_DEPTH:
            path, lineno = class_location[name]
            rel_path = path.relative_to(root).as_posix()
            findings.append(
                Finding("DEEP_INHERITANCE", rel_path, name, lineno, f"DIT={d} (máximo permitido {MAX_INHERITANCE_DEPTH})")
            )
    return findings


# ------------------------------------------------------------------------------
# 5. ORPHAN_PRIVATE_SYMBOL
# ------------------------------------------------------------------------------


def check_orphan_private_symbols(root: Path) -> list[Finding]:
    src_dir = root / "src"
    findings: list[Finding] = []

    for path in _iter_py_files(src_dir):
        tree = _parse(path)
        if tree is None:
            continue
        rel_path = path.relative_to(root).as_posix()

        declared: dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name.startswith("_") and not node.name.startswith("__"):
                    declared[node.name] = node.lineno

        if not declared:
            continue

        usage_count: dict[str, int] = dict.fromkeys(declared, 0)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in declared:
                usage_count[node.id] += 1
            elif isinstance(node, ast.Attribute) and node.attr in declared:
                usage_count[node.attr] += 1

        for name, lineno in declared.items():
            # La propia definición cuenta como 1 referencia (ast.Name no la captura para defs,
            # pero por robustez exigimos 0 usos reales fuera de la firma).
            if usage_count[name] == 0:
                findings.append(
                    Finding("ORPHAN_PRIVATE_SYMBOL", rel_path, name, lineno, "Declarado pero nunca referenciado en el módulo")
                )
    return findings


# ------------------------------------------------------------------------------
# 6. SPECULATIVE_MICRO_FILE
# ------------------------------------------------------------------------------


def check_speculative_micro_files(root: Path) -> list[Finding]:
    src_dir = root / "src"
    findings: list[Finding] = []

    for path in _iter_py_files(src_dir):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        loc = sum(1 for line in text.splitlines() if line.strip() and not line.strip().startswith("#"))
        if loc < MICRO_FILE_LOC_THRESHOLD:
            rel_path = path.relative_to(root).as_posix()
            findings.append(
                Finding("SPECULATIVE_MICRO_FILE", rel_path, path.name, 1, f"{loc} LOC (< {MICRO_FILE_LOC_THRESHOLD})")
            )
    return findings


# ------------------------------------------------------------------------------
# Orquestación
# ------------------------------------------------------------------------------


def scan_all(root_dir: Path | None = None) -> list[Finding]:
    root = root_dir or find_project_root()
    findings: list[Finding] = []
    findings.extend(check_unreachable_files(root))
    findings.extend(check_ghost_interfaces(root))
    findings.extend(check_middle_man_methods(root))
    findings.extend(check_deep_inheritance(root))
    findings.extend(check_orphan_private_symbols(root))
    findings.extend(check_speculative_micro_files(root))
    return findings


def format_findings(findings: list[Finding]) -> str:
    return "\n".join(f"  • [{f.kind}] {f.path}:{f.line} '{f.name}' — {f.detail}" for f in findings)


# ==============================================================================
# Suite de Pruebas Pytest (informativa, no bloqueante por defecto)
# ==============================================================================


def test_clean_design_report():
    """Reporta hallazgos de código muerto/sobreingeniería en src/ (no bloqueante por defecto)."""
    findings = scan_all()
    if findings:
        print(f"\n⚠️  {len(findings)} hallazgos de diseño detectados:\n{format_findings(findings)}")


# ==============================================================================
# CLI Runner Independiente
# ==============================================================================


def main() -> None:
    strict = "--strict" in sys.argv
    as_json = "--json" in sys.argv

    findings = scan_all()

    if as_json:
        print(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=2))
    else:
        print("=" * 70)
        print("🔍  DETECCIÓN DE CÓDIGO MUERTO Y SOBREINGENIERÍA")
        print("=" * 70)
        if findings:
            print(f"\n⚠️  {len(findings)} hallazgos:\n{format_findings(findings)}")
        else:
            print("\n✅ No se detectaron señales de código muerto ni sobreingeniería en src/.")
        print("=" * 70)

    if strict and findings:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

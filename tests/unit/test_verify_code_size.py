"""Tests unitarios para el script de verificación y auditoría de tamaño de código."""

from pathlib import Path

from scripts.verify_code_size import (
    DEFAULT_MAX_CLASS_LINES,
    DEFAULT_MAX_FILE_LINES,
    DEFAULT_MAX_FUNC_LINES,
    analyze_codebase,
)


def test_analyze_codebase_passes_on_compliant_code(tmp_path: Path):
    test_src = tmp_path / "src"
    test_src.mkdir()
    code = (
        "class ShortClass:\n"
        "    def method_one(self) -> int:\n"
        "        return 1\n"
        "\n"
        "def helper() -> str:\n"
        "    return 'ok'\n"
    )
    (test_src / "module.py").write_text(code, encoding="utf-8")

    result = analyze_codebase(test_src, max_file=50, max_class=30, max_func=10)

    assert len(result.violations) == 0
    assert len(result.files) == 1
    assert len(result.classes) == 1
    assert len(result.functions) == 2


def test_analyze_codebase_detects_oversized_file(tmp_path: Path):
    test_src = tmp_path / "src"
    test_src.mkdir()
    code = "\n".join(f"x_{i} = {i}" for i in range(25))
    (test_src / "big_file.py").write_text(code, encoding="utf-8")

    result = analyze_codebase(test_src, max_file=15, max_class=50, max_func=50)

    assert len(result.violations) == 1
    assert "[ARCHIVO EXCEDIDO]" in result.violations[0]


def test_analyze_codebase_detects_oversized_class(tmp_path: Path):
    test_src = tmp_path / "src"
    test_src.mkdir()
    body = "\n".join(f"    val_{i} = {i}" for i in range(25))
    code = f"class BigClass:\n{body}\n"
    (test_src / "big_class.py").write_text(code, encoding="utf-8")

    result = analyze_codebase(test_src, max_file=100, max_class=15, max_func=50)

    assert len(result.violations) == 1
    assert "[CLASE EXCEDIDA]" in result.violations[0]
    assert "BigClass" in result.violations[0]


def test_analyze_codebase_detects_oversized_function(tmp_path: Path):
    test_src = tmp_path / "src"
    test_src.mkdir()
    body = "\n".join(f"    a_{i} = {i}" for i in range(25))
    code = f"def big_function():\n{body}\n    return 0\n"
    (test_src / "big_func.py").write_text(code, encoding="utf-8")

    result = analyze_codebase(test_src, max_file=100, max_class=50, max_func=15)

    assert len(result.violations) == 1
    assert "[MÉTODO EXCEDIDO]" in result.violations[0]
    assert "big_function" in result.violations[0]


def test_current_src_codebase_complies_with_baseline():
    root_dir = Path(__file__).resolve().parent.parent.parent
    src_dir = root_dir / "src"

    result = analyze_codebase(
        src_dir=src_dir,
        max_file=DEFAULT_MAX_FILE_LINES,
        max_class=DEFAULT_MAX_CLASS_LINES,
        max_func=DEFAULT_MAX_FUNC_LINES,
        strict=False,
    )

    assert result.violations == [], f"Violaciones inesperadas en src/: {result.violations}"
    assert len(result.files) > 0

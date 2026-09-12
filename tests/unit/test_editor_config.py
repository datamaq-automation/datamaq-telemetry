"""tests/unit/test_editor_config.py — Convención de configuración de editor: alinear Pylance con pyrightconfig.json."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def test_pyrightconfig_excluye_tests():
    contenido = (RAIZ / "pyrightconfig.json").read_text(encoding="utf-8")
    assert '"exclude"' in contenido
    assert '"tests"' in contenido


def test_vscode_settings_excluye_tests():
    contenido = (RAIZ / ".vscode" / "settings.json").read_text(encoding="utf-8")
    assert "python.analysis.exclude" in contenido
    assert "tests" in contenido
    assert "venv" in contenido
    assert "**/__pycache__" in contenido


def test_gitignore_versiona_vscode_settings():
    contenido = (RAIZ / ".gitignore").read_text(encoding="utf-8")
    assert "!.vscode/settings.json" in contenido

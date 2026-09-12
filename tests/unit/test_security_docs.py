"""tests/unit/test_security_docs.py — Documentación defensiva (threat model presente)."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def test_readme_tiene_threat_model():
    contenido = (RAIZ / "README.md").read_text(encoding="utf-8")
    assert "Modelo de amenazas" in contenido
    assert "Seguridad" in contenido

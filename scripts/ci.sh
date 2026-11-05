#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR/.."

if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

export PYTHONPATH=.

echo "==> [1/6] Integridad: __init__.py de 0 bytes"
pytest tests/test_empty_inits.py -q

echo "==> [2/6] Estilo: ruff check + format"
ruff check .
ruff format --check .

echo "==> [3/6] Tipado: pyright"
pyright

echo "==> [4/6] Tests unitarios con cobertura (>=85%)"
pytest tests/unit -n auto --cov=src --cov-report=term-missing --cov-fail-under=85

echo "==> [5/6] Tests de integración"
pytest tests/integration -n auto -q

echo "==> [6/6] Reglas de Arquitectura y Tamaño de Código"
python scripts/verify_architecture.py
pytest tests/test_architecture.py -q
python scripts/verify_code_size.py

echo "Gauntlet superado."

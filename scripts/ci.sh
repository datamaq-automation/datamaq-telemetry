#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR/.."

if [ -d "venv" ]; then
    source venv/bin/activate
fi

export PYTHONPATH=.

echo "==> [1/5] Integridad: __init__.py de 0 bytes"
pytest tests/test_empty_inits.py -q

echo "==> [2/5] Estilo: ruff check + format"
ruff check .
ruff format --check .

echo "==> [3/5] Tipado: pyright"
pyright

echo "==> [4/5] Tests unitarios con cobertura (>=85%)"
pytest tests/unit --cov=src --cov-report=term-missing --cov-fail-under=85

echo "==> [5/5] Tests de integración"
pytest tests/integration -q

echo "Gauntlet superado."

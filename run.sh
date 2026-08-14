#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ -d "venv" ]; then
    source venv/bin/activate
fi

export PYTHONPATH=.
exec uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

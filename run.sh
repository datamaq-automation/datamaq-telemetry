#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

export PYTHONPATH=.

LOG_LEVEL_ARG="info"
EXTRA_ARGS=()

for arg in "$@"; do
    case $arg in
        --debug|-d)
            export APP_ENV="development"
            export LOG_LEVEL="DEBUG"
            export DEBUG="True"
            LOG_LEVEL_ARG="debug"
            ;;
        --log-level=*)
            export LOG_LEVEL="${arg#*=}"
            LOG_LEVEL_ARG="${arg#*=}"
            ;;
        *)
            EXTRA_ARGS+=("$arg")
            ;;
    esac
done

exec uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 --log-level "$LOG_LEVEL_ARG" "${EXTRA_ARGS[@]}"

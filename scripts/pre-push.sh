#!/usr/bin/env bash
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DIR/.." && pwd)"
cd "$ROOT_DIR"

if [ -d "venv" ]; then
    source venv/bin/activate
fi

export PYTHONPATH=.

# Paleta de colores ANSI
BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
RESET='\033[0m'

_time_now() {
    python3 -c "import time; print(f'{time.time():.2f}')"
}

_calc_duration() {
    python3 -c "t0=$1; t1=$2; diff=t1-t0; mins=int(diff//60); secs=diff%60; print(f'{mins}m {secs:.1f}s' if mins>0 else (f'{secs:.1f}s' if secs>=1 else f'{secs*1000:.0f}ms'))"
}

START_ALL=$(_time_now)

echo -e "${BOLD}${CYAN}======================================================================${RESET}"
echo -e "${BOLD}${CYAN}  ⚡ DATAMAQ TELEMETRY — GAUNTLET PRE-PUSH (VERIFICACIÓN LOCAL)       ${RESET}"
echo -e "${BOLD}${CYAN}======================================================================${RESET}"

TOTAL_STAGES=7

run_stage() {
    local num="$1"
    local title="$2"
    local cmd="$3"

    echo -e "\n${BOLD}${CYAN}==> [${num}/${TOTAL_STAGES}] ${title}${RESET}"
    local t_start=$(_time_now)

    if eval "$cmd"; then
        local t_end=$(_time_now)
        local dur=$(_calc_duration "$t_start" "$t_end")
        echo -e "${GREEN}✓ [PASS] Stage ${num}/${TOTAL_STAGES} (${title}) superado en ${dur}${RESET}"
    else
        local t_end=$(_time_now)
        local dur=$(_calc_duration "$t_start" "$t_end")
        echo -e "${RED}✗ [FAIL] Stage ${num}/${TOTAL_STAGES} (${title}) falló tras ${dur}${RESET}"
        return 1
    fi
}

# Stage 0: Secretos — ver scripts/guard_secrets.sh para el origen (D-2)
run_stage "0" "Guard: sin .env reales trackeados" "bash scripts/guard_secrets.sh"

# Stage 1: Integridad
run_stage "1" "Integridad: __init__.py de 0 bytes" "pytest tests/test_empty_inits.py -q --no-header"

# Stage 2: Estilo y Formato
run_stage "2" "Estilo & Formato: ruff check + format" "ruff check . && ruff format --check ."

# Stage 3: Tipado Estricto
run_stage "3" "Tipado Estricto: pyright" "pyright"

# Stage 4: Tests Unitarios con Cobertura
run_stage "4" "Tests Unitarios & Cobertura (>=85%)" "pytest tests/unit -n auto --cov=src --cov-report=term-missing:skip-covered --cov-fail-under=85 -o console_output_style=progress"

# Stage 5: Tests de Integración
run_stage "5" "Tests de Integración" "pytest tests/integration -n auto -q --no-header"

# Stage 6: Reglas de Arquitectura y Tamaño
run_stage "6" "Clean Architecture & Tamaño de Código" "python3 scripts/verify_architecture.py && python3 scripts/verify_code_size.py"

END_ALL=$(_time_now)
TOTAL_DUR=$(_calc_duration "$START_ALL" "$END_ALL")

echo -e "\n${BOLD}${GREEN}======================================================================${RESET}"
echo -e "${BOLD}${GREEN}  ✓ GAUNTLET PRE-PUSH SUPERADO — Tiempo total local: ${TOTAL_DUR}  ${RESET}"
echo -e "${BOLD}${GREEN}======================================================================${RESET}\n"

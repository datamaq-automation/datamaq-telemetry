#!/usr/bin/env bash
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DIR/.." && pwd)"
cd "$ROOT_DIR"

if [ -d ".venv" ]; then
    # Mismo Python que CI y producción (3.12): un gauntlet local en otra versión puede dar
    # verde donde CI/prod fallan, o al revés.
    .venv/bin/python -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))' \
        || { echo "ERROR: .venv no es Python 3.12. Recrearlo (ver README §1)."; exit 1; }
    source .venv/bin/activate
    # `source activate` no garantiza que .venv/bin quede primero en PATH (algunos shells
    # reordenan tras el activate, ej. ~/.local/bin adelante) — sin esto, "pytest"/"pyright"
    # a secas pueden resolver a un binario global sin las dependencias del proyecto
    # instaladas, y el gauntlet falla con ImportError en vez de con un resultado real.
    export PATH="$ROOT_DIR/.venv/bin:$PATH"
    # Aviso (no bloquea): paquetes cuya versión instalada difiere de requirements.lock.
    python3 - <<'PY' || true
import re
from importlib.metadata import PackageNotFoundError, version
distintos = []
for linea in open("requirements.lock"):
    m = re.match(r"^([A-Za-z0-9_.-]+)(\[[^]]*\])?==(\S+)", linea)
    if not m:
        continue
    try:
        instalada = version(m.group(1))
    except PackageNotFoundError:
        instalada = "ausente"
    if instalada != m.group(3):
        distintos.append(f"{m.group(1)} (lock {m.group(3)}, .venv {instalada})")
if distintos:
    print("AVISO: .venv no coincide con requirements.lock -> uv pip sync --python .venv/bin/python requirements.lock")
    print("  " + ", ".join(distintos))
PY
elif [ -z "$CI" ]; then
    # En CI (nightly) no hay .venv: usa el Python de setup-python. En local es obligatorio.
    echo "ERROR: falta .venv. Crearlo con Python 3.12 (ver README §1)."
    exit 1
fi

# Invocación por módulo (`python3 -m X`), no el script `.venv/bin/X`: si el repo se movió
# de carpeta después de crear el venv, el shebang de esos scripts queda apuntando a la
# ruta vieja ("bad interpreter") mientras que `.venv/bin/python3` (symlink al intérprete)
# sigue siendo válido.
PYTEST="python3 -m pytest"
PYRIGHT="python3 -m pyright"

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

# Detección de cambios de configuración (GitOps) vs código de producto
UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || echo "origin/main")
CHANGED_FILES=$(git diff --name-only "$UPSTREAM"...HEAD 2>/dev/null || true)

if [ -z "$CHANGED_FILES" ]; then
    CHANGED_FILES=$(git diff --name-only --cached 2>/dev/null || true)
fi
if [ -z "$CHANGED_FILES" ]; then
    CHANGED_FILES=$(git diff --name-only 2>/dev/null || true)
fi
if [ -z "$CHANGED_FILES" ]; then
    CHANGED_FILES=$(git diff --name-only HEAD~1 HEAD 2>/dev/null || true)
fi

ES_SOLO_CONFIG=false
if [ -n "$CHANGED_FILES" ]; then
    if ! echo "$CHANGED_FILES" | grep -qvE "^data/|^docs/|\.md$|^tests/unit/test_yaml_|^tests/unit/test_verificador_unifilar"; then
        ES_SOLO_CONFIG=true
    fi
fi

if [ "$ES_SOLO_CONFIG" = true ]; then
    echo -e "${BOLD}${YELLOW}ℹ Modo GitOps detectado (solo configuración YAML / docs). Ejecutando verificación rápida...${RESET}"
    
    # 1. Guard de secretos
    bash scripts/guard_secrets.sh
    
    # 2. Validación de sintaxis YAML
    python3 -c "import glob, yaml; [yaml.safe_load(open(f)) for f in glob.glob('data/*.yml') + glob.glob('data/*.yaml')]"
    
    # 3. Tests específicos de configuración y repositorio YAML
    $PYTEST tests/unit/test_yaml_organizaciones_repository.py tests/unit/test_verificador_unifilar.py -q --no-header
    
    END_ALL=$(_time_now)
    TOTAL_DUR=$(_calc_duration "$START_ALL" "$END_ALL")
    echo -e "\n${BOLD}${GREEN}======================================================================${RESET}"
    echo -e "${BOLD}${GREEN}  ✓ GAUNTLET RÁPIDO (GITOPS CONFIG) SUPERADO — Tiempo total: ${TOTAL_DUR}  ${RESET}"
    echo -e "${BOLD}${GREEN}======================================================================${RESET}\n"
    exit 0
fi

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
run_stage "1" "Integridad: __init__.py de 0 bytes" "$PYTEST tests/test_empty_inits.py -q --no-header"

# Stage 2: Estilo y Formato
run_stage "2" "Estilo & Formato: ruff check + format" "ruff check . && ruff format --check ."

# Stage 3: Tipado Estricto
run_stage "3" "Tipado Estricto: pyright" "$PYRIGHT"

# Stage 4: Tests Unitarios con Cobertura
run_stage "4" "Tests Unitarios & Cobertura (>=85%)" "$PYTEST tests/unit -n auto --cov=src --cov-report=term-missing:skip-covered --cov-fail-under=85 -o console_output_style=progress"

# Stage 5: Tests de Integración
run_stage "5" "Tests de Integración" "$PYTEST tests/integration -n auto -q --no-header"

# Stage 6: Reglas de Arquitectura y Tamaño
run_stage "6" "Clean Architecture & Tamaño de Código" "python3 scripts/verify_architecture.py && python3 scripts/verify_code_size.py"

END_ALL=$(_time_now)
TOTAL_DUR=$(_calc_duration "$START_ALL" "$END_ALL")

echo -e "\n${BOLD}${GREEN}======================================================================${RESET}"
echo -e "${BOLD}${GREEN}  ✓ GAUNTLET PRE-PUSH SUPERADO — Tiempo total local: ${TOTAL_DUR}  ${RESET}"
echo -e "${BOLD}${GREEN}======================================================================${RESET}\n"

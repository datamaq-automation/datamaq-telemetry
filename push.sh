#!/usr/bin/env bash
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Paleta de colores ANSI
BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
RESET='\033[0m'

_time_now() {
    python3 -c "import time; print(f'{time.time():.2f}')"
}

_calc_duration() {
    python3 -c "t0=$1; t1=$2; diff=t1-t0; mins=int(diff//60); secs=diff%60; print(f'{mins}m {secs:.1f}s' if mins>0 else (f'{secs:.1f}s' if secs>=1 else f'{secs*1000:.0f}ms'))"
}

START_PUSH=$(_time_now)

COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "HEAD")
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")

echo -e "${BOLD}${CYAN}======================================================================${RESET}"
echo -e "${BOLD}${CYAN}  🚀 DATAMAQ TELEMETRY — PUSH & DESPLIEGUE CONTINUO EN VIVO (CI/CD)  ${RESET}"
echo -e "${BOLD}${CYAN}  Commit: ${YELLOW}${COMMIT_SHA}${CYAN} | Rama: ${YELLOW}${BRANCH}${CYAN}                                 ${RESET}"
echo -e "${BOLD}${CYAN}======================================================================${RESET}\n"

echo -e "${BOLD}${CYAN}==> [1/2] Gauntlet Local & Push a Git Remoto${RESET}"
t0=$(_time_now)

if git push "$@"; then
    t1=$(_time_now)
    dur=$(_calc_duration "$t0" "$t1")
    echo -e "\n${BOLD}${GREEN}✓ [PASS] Push realizado a GitHub en ${dur}.${RESET}\n"
else
    t1=$(_time_now)
    dur=$(_calc_duration "$t0" "$t1")
    echo -e "\n${BOLD}${RED}✗ [FAIL] El push a Git falló tras ${dur}.${RESET}\n"
    exit 1
fi

echo -e "${BOLD}${CYAN}==> [2/2] Monitoreo en Vivo de CI/CD Deploy a VPS${RESET}"
python3 scripts/watch_deploy.py

END_PUSH=$(_time_now)
TOTAL_PUSH_DUR=$(_calc_duration "$START_PUSH" "$END_PUSH")

echo -e "${BOLD}${GREEN}======================================================================${RESET}"
echo -e "${BOLD}${GREEN}  ✓ PROCESO COMPLETO FINALIZADO CON ÉXITO — Duración Total: ${TOTAL_PUSH_DUR}  ${RESET}"
echo -e "${BOLD}${GREEN}======================================================================${RESET}\n"

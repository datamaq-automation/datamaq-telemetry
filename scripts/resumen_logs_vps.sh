#!/usr/bin/env bash
# ==============================================================================
# Resumen de las últimas 24 h de los logs del VPS, por servicio y por evento.
# SOLO LECTURA: ejecuta `journalctl -o json` por ssh; no escribe nada en la VPS
# ni reinicia servicios. El desglose lo hace scripts/resumen_logs_vps.py.
# ==============================================================================
# Uso:
#   ./scripts/resumen_logs_vps.sh          # bloque legible en terminal
#   ./scripts/resumen_logs_vps.sh --plano  # texto plano (cuerpo de mensaje Telegram)
# Variables:
#   VPS_HOST   alias ssh de la VPS (default: vps-datamaq)
# ==============================================================================
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VPS_HOST="${VPS_HOST:-vps-datamaq}"
UNIDADES=(datamaq-telemetry.service isftn199.service eitec.service cybersyn.service)

PLANO=()
for arg in "$@"; do
    case "$arg" in
        --plano) PLANO=(--plano) ;;
        -h | --help)
            sed -n '2,11p' "$0"
            exit 0
            ;;
        *)
            echo "Opción desconocida: $arg (usa --help)" >&2
            exit 2
            ;;
    esac
done

for unidad in "${UNIDADES[@]}"; do
    ssh -o BatchMode=yes -o ConnectTimeout=10 "$VPS_HOST" \
        "journalctl -u $unidad --since '-24h' -o json --no-pager -q" |
        python3 -I "$DIR/scripts/resumen_logs_vps.py" --unit "$unidad" "${PLANO[@]}"
    echo
done

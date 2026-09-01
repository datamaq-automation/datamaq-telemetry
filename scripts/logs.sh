#!/usr/bin/env bash
# ==============================================================================
# Script para inspeccionar, seguir y descargar logs del VPS (datamaq-telemetry)
# ==============================================================================
# Uso:
#   ./scripts/logs.sh                  # Últimas 100 líneas del log del backend
#   ./scripts/logs.sh -f               # Streaming en vivo (follow)
#   ./scripts/logs.sh -n 300           # Últimas 300 líneas
#   ./scripts/logs.sh --since "1h ago" # Logs desde hace 1 hora
#   ./scripts/logs.sh --status         # Estado del servicio systemd, memoria y sockets
#   ./scripts/logs.sh --mqtt           # Logs del broker MQTT Mosquitto (archivo, no journald)
#   ./scripts/logs.sh --mqtt --device  # Solo eventos de medidores en el broker (filtra escaneres)
#   ./scripts/logs.sh --save           # Descargar logs a un archivo local con timestamp
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

if [ -f "scripts/.env.deploy" ]; then
    # shellcheck source=/dev/null
    source scripts/.env.deploy
fi

SSH_HOST="${DEPLOY_SSH_HOST:-}"
SSH_PORT="${DEPLOY_SSH_PORT:-22}"
SSH_USER="${DEPLOY_SSH_USER:-}"
SERVICE_NAME="${DEPLOY_SERVICE_NAME:-datamaq-telemetry.service}"

mostrar_ayuda() {
    echo "Uso: $0 [OPCIONES]"
    echo ""
    echo "Opciones:"
    echo "  -f, --follow           Seguir logs en tiempo real (tail -f)."
    echo "  -n, --lines N          Cantidad de líneas a mostrar (default: 100)."
    echo "  -s, --since TIEMPO     Filtrar logs desde un momento (ej: '10 min ago', '1 hour ago', 'today')."
    echo "  --status               Mostrar estado completo del servicio (systemctl status, sockets, memoria)."
    echo "  --mqtt                 Mostrar logs del broker Mosquitto en lugar del backend."
    echo "  --device [UID]         Con --mqtt: filtrar solo eventos de medidores (opcional: un UID/MAC)."
    echo "  --save [ARCHIVO]       Descargar logs a un archivo local (default: logs_vps_TIMESTAMP.log)."
    echo "  --host HOST            Sobrescribir host SSH."
    echo "  --user USER            Sobrescribir usuario SSH."
    echo "  --port PORT            Sobrescribir puerto SSH."
    echo "  -h, --help             Mostrar esta ayuda."
    echo ""
    echo "Configuración:"
    echo "  Las credenciales pueden definirse en 'scripts/.env.deploy':"
    echo "    DEPLOY_SSH_HOST=tuhost.com"
    echo "    DEPLOY_SSH_PORT=22"
    echo "    DEPLOY_SSH_USER=tu_usuario"
    echo "    DEPLOY_SERVICE_NAME=datamaq-telemetry.service"
}

MODO="tail"
LINEAS=100
MQTT_LOG="/var/log/mosquitto/mosquitto.log"
USAR_MQTT=""
DEVICE_FILTRO=""
SINCE=""
FOLLOW=""
SAVE_FILE=""
TARGET_SERVICE="$SERVICE_NAME"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--follow)
            FOLLOW="-f"
            shift
            ;;
        -n|--lines)
            LINEAS="$2"
            shift 2
            ;;
        -s|--since)
            SINCE="--since \"$2\""
            shift 2
            ;;
        --status)
            MODO="status"
            shift
            ;;
        --mqtt)
            USAR_MQTT="1"
            TARGET_SERVICE="mosquitto.service"
            shift
            ;;
        --device)
            USAR_MQTT="1"
            TARGET_SERVICE="mosquitto.service"
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                DEVICE_FILTRO="$2"
                shift 2
            else
                DEVICE_FILTRO="__TODOS__"
                shift
            fi
            ;;
        --save)
            MODO="save"
            if [[ -n "$2" && ! "$2" =~ ^- ]]; then
                SAVE_FILE="$2"
                shift 2
            else
                SAVE_FILE="logs_vps_$(date +'%Y%m%d_%H%M%S').log"
                shift
            fi
            ;;
        --host)
            SSH_HOST="$2"
            shift 2
            ;;
        --user)
            SSH_USER="$2"
            shift 2
            ;;
        --port)
            SSH_PORT="$2"
            shift 2
            ;;
        -h|--help)
            mostrar_ayuda
            exit 0
            ;;
        *)
            echo "Opción desconocida: $1"
            mostrar_ayuda
            exit 1
            ;;
    esac
done

if [ -z "$SSH_HOST" ] || [ -z "$SSH_USER" ]; then
    echo "ERROR: Faltan variables de conexión SSH (DEPLOY_SSH_HOST y DEPLOY_SSH_USER)."
    echo "Definilas en 'scripts/.env.deploy' o pasalas con --host y --user."
    exit 1
fi


# Mosquitto escribe a archivo (log_dest file en /etc/mosquitto/conf.d/datamaq.conf),
# no a journald: `journalctl -u mosquitto` devuelve "No entries".
construir_cmd_mqtt() {
    local seguir="$1"
    local filtro=""

    if [ "$DEVICE_FILTRO" = "__TODOS__" ]; then
        # Eventos de clientes reales; descarta los escáneres de internet (<unknown>).
        filtro=" | grep -aE 'New client connected|has exceeded timeout|Socket error on client|Client .* disconnected' | grep -av '<unknown>'"
    elif [ -n "$DEVICE_FILTRO" ]; then
        filtro=" | grep -a '$DEVICE_FILTRO'"
    fi

    if [ -n "$seguir" ]; then
        echo "sudo tail -n $LINEAS -f $MQTT_LOG$filtro"
    else
        echo "sudo tail -n $LINEAS $MQTT_LOG$filtro"
    fi
}

case "$MODO" in
    status)
        echo "==> Consultando estado del servicio $TARGET_SERVICE en $SSH_USER@$SSH_HOST:$SSH_PORT..."
        ssh -p "$SSH_PORT" "$SSH_USER@$SSH_HOST" "
            echo '--- [Systemd Service Status] ---'
            sudo systemctl status $TARGET_SERVICE --no-pager || true
            echo ''
            echo '--- [Uso de Memoria y CPU] ---'
            ps aux | grep -E 'uvicorn|fastapi|datamaq' | grep -v grep || true
            echo ''
            echo '--- [Puertos en Escucha] ---'
            sudo ss -tulpn | grep -E '8000|8883|1883' || true
        "
        ;;
    save)
        echo "==> Descargando últimas $LINEAS líneas de $TARGET_SERVICE a $SAVE_FILE..."
        if [ -n "$USAR_MQTT" ]; then
            CMD="$(construir_cmd_mqtt "")"
        else
            CMD="journalctl -u $TARGET_SERVICE -n $LINEAS --no-pager $SINCE"
        fi
        ssh -p "$SSH_PORT" "$SSH_USER@$SSH_HOST" "$CMD" > "$SAVE_FILE"
        echo "==> Logs guardados exitosamente en: $SAVE_FILE ($(wc -l < "$SAVE_FILE") líneas)"
        ;;
    tail)
        echo "==> Conectando a $SSH_USER@$SSH_HOST:$SSH_PORT para ver logs de $TARGET_SERVICE..."
        if [ -n "$USAR_MQTT" ]; then
            [ -n "$SINCE" ] && echo "[i] --since no aplica al log de Mosquitto (es un archivo); usá -n para acotar."
            CMD="$(construir_cmd_mqtt "$FOLLOW")"
        else
            CMD="journalctl -u $TARGET_SERVICE -n $LINEAS --no-pager $FOLLOW $SINCE"
            if [ -n "$FOLLOW" ]; then
                CMD="journalctl -u $TARGET_SERVICE -n $LINEAS -f $SINCE"
            fi
        fi
        ssh -t -p "$SSH_PORT" "$SSH_USER@$SSH_HOST" "$CMD"
        ;;
esac

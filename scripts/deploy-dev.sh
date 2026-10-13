#!/usr/bin/env bash
# ==============================================================================
# Despliegue del backend de DEV (api-dev.datamaq.com.ar). NO es el CD de producción.
# ==============================================================================
# Decisión: decisions/2026-10-13_sin-publicar-hasta-entorno-dev.md y spec-api-dev.md (D1).
# - Código: rama `develop` del checkout de dev (nunca `main` del de producción).
# - Datos: checkout propio de datamaq-data de dev, en `main` (Q7).
# - No toca deploy.yml ni scripts/deploy-server.sh.
#
# Uso:
#   DEV_SSH_HOST=... DEV_SSH_PORT=22 DEV_SSH_USER=... ./scripts/deploy-dev.sh
#   DEV_DRY_RUN=1 ... ./scripts/deploy-dev.sh   # valida guardas e imprime el plan, sin SSH
#
# Variables (con valores por defecto de dev):
#   DEV_REMOTE_DIR     /var/www/datamaq-dev/app
#   DEV_SERVICE_NAME   datamaq-dev.service
#   DEV_HEALTH_URL     http://127.0.0.1:8005/health
#   DEV_RUN_AS         datamaq-dev   (git y venv corren como el usuario de servicio)
#
# Guardas (abortan antes de cualquier SSH): destino de producción, usuario root,
# servicio que no sea el de dev, puerto de producción en el health.
# ==============================================================================
set -euo pipefail

PROD_REMOTE_DIR="/var/www/datamaq-telemetry"
PROD_SERVICE="datamaq-telemetry.service"
PROD_PORT="8885"

DEV_REMOTE_DIR="${DEV_REMOTE_DIR:-/var/www/datamaq-dev/app}"
DEV_SERVICE_NAME="${DEV_SERVICE_NAME:-datamaq-dev.service}"
DEV_HEALTH_URL="${DEV_HEALTH_URL:-http://127.0.0.1:8005/health}"
DEV_RUN_AS="${DEV_RUN_AS:-datamaq-dev}"
DEV_SSH_HOST="${DEV_SSH_HOST:-}"
DEV_SSH_PORT="${DEV_SSH_PORT:-22}"
DEV_SSH_USER="${DEV_SSH_USER:-}"

log() { echo "[deploy-dev] $*"; }
fallar() { echo "[deploy-dev] ERROR: $*" >&2; exit 1; }

validar_guardas() {
    [ -n "$DEV_SSH_HOST" ] || fallar "falta DEV_SSH_HOST"
    [ -n "$DEV_SSH_USER" ] || fallar "falta DEV_SSH_USER"
    [ "$DEV_SSH_USER" != "root" ] || fallar "no se despliega como root (rompe ownership de .git)"
    [ "$DEV_REMOTE_DIR" != "$PROD_REMOTE_DIR" ] || fallar "DEV_REMOTE_DIR apunta a producción ($PROD_REMOTE_DIR)"
    case "$DEV_REMOTE_DIR" in
        *datamaq-dev*) ;;
        *) fallar "DEV_REMOTE_DIR debe estar bajo datamaq-dev: $DEV_REMOTE_DIR" ;;
    esac
    [ "$DEV_SERVICE_NAME" != "$PROD_SERVICE" ] || fallar "DEV_SERVICE_NAME es el servicio de producción"
    case "$DEV_SERVICE_NAME" in
        datamaq-dev*.service) ;;
        *) fallar "DEV_SERVICE_NAME debe ser datamaq-dev*.service: $DEV_SERVICE_NAME" ;;
    esac
    case "$DEV_HEALTH_URL" in
        *":$PROD_PORT"*) fallar "DEV_HEALTH_URL usa el puerto de producción ($PROD_PORT)" ;;
    esac
}

validar_guardas

if [ "${DEV_DRY_RUN:-0}" = "1" ]; then
    log "guardas OK. Plan (sin SSH):"
    log "  destino: $DEV_SSH_USER@$DEV_SSH_HOST:$DEV_SSH_PORT  dir: $DEV_REMOTE_DIR"
    log "  código: git checkout develop (como $DEV_RUN_AS), datos: data/ en main"
    log "  venv: uv pip sync requirements.lock; reinicio: $DEV_SERVICE_NAME; health: $DEV_HEALTH_URL"
    exit 0
fi

log "desplegando en $DEV_SSH_HOST (dir $DEV_REMOTE_DIR, servicio $DEV_SERVICE_NAME)"

COMANDO_REMOTO="DEV_REMOTE_DIR=$(printf %q "$DEV_REMOTE_DIR") DEV_SERVICE_NAME=$(printf %q "$DEV_SERVICE_NAME") DEV_HEALTH_URL=$(printf %q "$DEV_HEALTH_URL") DEV_RUN_AS=$(printf %q "$DEV_RUN_AS") bash -s"

ssh -T -p "$DEV_SSH_PORT" "$DEV_SSH_USER@$DEV_SSH_HOST" "$COMANDO_REMOTO" <<'REMOTO'
set -euo pipefail
cd "$DEV_REMOTE_DIR"

# La base que usa el servicio debe ser la de dev. Solo se revisa el nombre: no se lee ni imprime la contraseña.
if ! sudo -u "$DEV_RUN_AS" grep -q '^DB_NAME=datamaq_dev$' .env; then
    echo "[deploy-dev] ERROR: .env no define DB_NAME=datamaq_dev (la app ignora DATABASE_URL)" >&2
    exit 1
fi

sudo -u "$DEV_RUN_AS" git fetch origin
sudo -u "$DEV_RUN_AS" git checkout develop
sudo -u "$DEV_RUN_AS" git pull --ff-only origin develop

# Datos maestros de dev: checkout propio en main (Q7).
sudo -u "$DEV_RUN_AS" git -C data fetch origin
sudo -u "$DEV_RUN_AS" git -C data checkout main
sudo -u "$DEV_RUN_AS" git -C data pull --ff-only origin main

sudo -u "$DEV_RUN_AS" uv pip sync --python .venv/bin/python requirements.lock

sudo systemctl restart "$DEV_SERVICE_NAME"

for intento in 1 2 3 4 5 6; do
    if curl -fsS -o /dev/null "$DEV_HEALTH_URL"; then
        echo "[deploy-dev] health OK en intento $intento"
        exit 0
    fi
    sleep 5
done
echo "[deploy-dev] ERROR: health no respondió en $DEV_HEALTH_URL" >&2
exit 1
REMOTO

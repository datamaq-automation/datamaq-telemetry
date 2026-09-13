#!/bin/bash
set -e

# Deploy server de datamaq-telemetry al VPS (git pull + deps + restart + health + rollback).
# Requiere bootstrap previo en el VPS: clon del repo, .venv, systemd service,
# base de datos y .env (ver docs/CD.md).

if [ -f "scripts/.env.deploy" ]; then
    source scripts/.env.deploy
fi

if [ -z "$DEPLOY_SSH_HOST" ] || [ -z "$DEPLOY_SSH_PORT" ] || [ -z "$DEPLOY_SSH_USER" ] || [ -z "$DEPLOY_REMOTE_DIR" ] || [ -z "$DEPLOY_SERVICE_NAME" ]; then
    echo "Error: faltan variables de configuración del deploy."
    echo "Definilas en scripts/.env.deploy o como variables de entorno:"
    echo "  DEPLOY_SSH_HOST, DEPLOY_SSH_PORT, DEPLOY_SSH_USER, DEPLOY_REMOTE_DIR, DEPLOY_SERVICE_NAME"
    exit 1
fi

if [ "$DEPLOY_SSH_USER" = "root" ]; then
    echo "Error: no se permite desplegar como root. Usá un usuario dedicado."
    exit 1
fi

# Guard: prohibido ejecutar el deploy desde el propio VPS.
LOCAL_NAMES="$(hostname 2>/dev/null || true) $(hostname -f 2>/dev/null || true) $(hostname -I 2>/dev/null || true)"
case " $LOCAL_NAMES " in
    *" $DEPLOY_SSH_HOST "*)
        echo "Error: no ejecutar deploy-server.sh dentro del VPS."
        echo "El host destino ($DEPLOY_SSH_HOST) coincide con este equipo."
        echo "Usá el workflow 'CD Deploy' de GitHub Actions."
        exit 1
        ;;
esac

HEALTH_URL="${DEPLOY_HEALTH_URL:-http://localhost:8000/health/ready}"

log() { echo "[$(date +"%Y-%m-%dT%H:%M:%S")] $1"; }

log "Iniciando despliegue de datamaq-telemetry en $DEPLOY_SSH_HOST..."

ssh -A -o ForwardAgent=yes -T -p "$DEPLOY_SSH_PORT" "$DEPLOY_SSH_USER@$DEPLOY_SSH_HOST" \
    DEPLOY_REMOTE_DIR="$DEPLOY_REMOTE_DIR" \
    DEPLOY_SERVICE_NAME="$DEPLOY_SERVICE_NAME" \
    HEALTH_URL="$HEALTH_URL" \
    GITHUB_TOKEN="$GITHUB_TOKEN" \
    GITHUB_REPOSITORY="$GITHUB_REPOSITORY" \
    bash <<'EOF'
    set -e

    echo "==> Cambiando a $DEPLOY_REMOTE_DIR"
    cd "$DEPLOY_REMOTE_DIR" || { echo "Error: no se pudo entrar a $DEPLOY_REMOTE_DIR"; exit 1; }

    echo "==> Guardando commit actual para posible rollback..."
    PREVIOUS_COMMIT=$(git rev-parse HEAD)

    echo "==> Respaldando dependencias actuales (para rollback)..."
    ./.venv/bin/pip freeze > /tmp/telemetry-deps.txt

    echo "==> Actualizando código (fast-forward only)..."
    if [ -n "$GITHUB_TOKEN" ] && [ -n "$GITHUB_REPOSITORY" ]; then
        git pull --ff-only "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" main
    else
        git pull --ff-only
    fi

    echo "==> Instalando dependencias..."
    ./.venv/bin/pip install -r requirements.txt

    echo "==> Backup de la base antes de migrar (D-5)..."
    source .env
    BACKUP_DIR="/tmp/datamaq-telemetry-pre-migracion"
    mkdir -p "$BACKUP_DIR"
    BACKUP_FILE="$BACKUP_DIR/pre_migracion_$(date +%Y%m%d_%H%M%S).sql.gz"
    mysqldump --add-drop-table -h"$DB_HOST" -u"$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" | gzip > "$BACKUP_FILE"
    echo "Backup: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
    # Retención corta: solo para el rollback inmediato de este deploy, no reemplaza
    # el backup diario con retención larga fuera del VPS (D-6).
    ls -t "$BACKUP_DIR"/pre_migracion_*.sql.gz 2>/dev/null | tail -n +6 | xargs -r rm --

    echo "==> Deteniendo servicio antes de migrar (evita escrituras concurrentes durante el ALTER)..."
    sudo systemctl stop "$DEPLOY_SERVICE_NAME"

    echo "==> Aplicando migraciones de base de datos (Alembic)..."
    if ! ./.venv/bin/alembic upgrade head; then
        echo "ERROR: la migración falló. Restaurando base ($BACKUP_FILE) y código anterior..."
        gunzip -c "$BACKUP_FILE" | mysql -h"$DB_HOST" -u"$DB_USER" -p"$DB_PASSWORD" "$DB_NAME"
        git reset --hard "$PREVIOUS_COMMIT"
        ./.venv/bin/pip install -r /tmp/telemetry-deps.txt
        sudo systemctl start "$DEPLOY_SERVICE_NAME"
        echo "ERROR: Deploy fallido en la migración. Rollback de base y código ejecutado."
        exit 1
    fi

    echo "==> Iniciando servicio $DEPLOY_SERVICE_NAME..."
    sudo systemctl start "$DEPLOY_SERVICE_NAME"

    echo "==> Verificando salud del servicio vía HTTP ($HEALTH_URL)..."
    MAX_WAIT=30
    INTERVAL=2
    ATTEMPTS=$((MAX_WAIT / INTERVAL))
    HEALTH_OK=false

    for i in $(seq 1 "$ATTEMPTS"); do
        sleep "$INTERVAL"
        HTTP_STATUS=$(./.venv/bin/python3 -c "import urllib.request; print(urllib.request.urlopen('$HEALTH_URL', timeout=5).status)" 2>/dev/null || echo "000")
        if [[ "$HTTP_STATUS" == "200" ]]; then
            HEALTH_OK=true
            echo "Health-check OK (HTTP 200) en el intento $i."
            break
        fi
        echo "Intento $i/$ATTEMPTS: servicio no responde con HTTP 200 (status: $HTTP_STATUS). Reintentando..."
    done

    if [ "$HEALTH_OK" != true ]; then
        echo "ERROR: El health-check falló después de ${MAX_WAIT}s. Ejecutando rollback completo (base + código) a $PREVIOUS_COMMIT..."
        sudo systemctl stop "$DEPLOY_SERVICE_NAME"
        gunzip -c "$BACKUP_FILE" | mysql -h"$DB_HOST" -u"$DB_USER" -p"$DB_PASSWORD" "$DB_NAME"
        git reset --hard "$PREVIOUS_COMMIT"
        ./.venv/bin/pip install -r /tmp/telemetry-deps.txt
        sudo systemctl start "$DEPLOY_SERVICE_NAME"
        echo "ERROR: Deploy fallido. Rollback ejecutado (base, código y dependencias)."
        exit 1
    fi

    echo "==> Verificando estado del servicio..."
    sudo systemctl is-active "$DEPLOY_SERVICE_NAME"
EOF

if [ $? -eq 0 ]; then
    log "Despliegue exitoso."
else
    log "ERROR: El despliegue falló."
    exit 1
fi

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

HEALTH_URL="${DEPLOY_HEALTH_URL:-http://127.0.0.1:8885/health}"

# Rama a desplegar. Producción usa main (valor por defecto); staging usa develop. Va sin comillas en el comando ssh,
# así que se valida: solo nombres de rama seguros.
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
if ! [[ "$DEPLOY_BRANCH" =~ ^[A-Za-z0-9._/-]+$ ]]; then
    echo "Error: DEPLOY_BRANCH inválido: '$DEPLOY_BRANCH'."
    exit 1
fi

log() { echo "[$(date +"%Y-%m-%dT%H:%M:%S")] $1"; }

log "Iniciando despliegue de datamaq-telemetry en $DEPLOY_SSH_HOST..."

ssh -A -o ForwardAgent=yes -T -p "$DEPLOY_SSH_PORT" "$DEPLOY_SSH_USER@$DEPLOY_SSH_HOST" \
    DEPLOY_REMOTE_DIR="$DEPLOY_REMOTE_DIR" \
    DEPLOY_SERVICE_NAME="$DEPLOY_SERVICE_NAME" \
    DEPLOY_BRANCH="$DEPLOY_BRANCH" \
    DEPLOY_BACKUP_DIR="${DEPLOY_BACKUP_DIR:-}" \
    DEPLOY_DEPS_FILE="${DEPLOY_DEPS_FILE:-}" \
    HEALTH_URL="$HEALTH_URL" \
    GITHUB_TOKEN="$GITHUB_TOKEN" \
    GITHUB_REPOSITORY="$GITHUB_REPOSITORY" \
    bash <<'EOF'
    # -E: el trap ERR también corre dentro de funciones. pipefail: un `mysqldump` que falla no queda tapado por
    # el `| gzip` que termina bien (#17). umask 022: el código que escribe git tiene que quedar legible por el usuario
    # del servicio (#15: con 077, server.py quedó 0600 y el servicio no arrancó). Los dumps y el freeze de pip se
    # crean con modo 600 explícito (install -m 600), no con umask.
    set -Eeuo pipefail
    umask 022
    DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"

    echo "==> Cambiando a $DEPLOY_REMOTE_DIR"
    cd "$DEPLOY_REMOTE_DIR" || { echo "Error: no se pudo entrar a $DEPLOY_REMOTE_DIR"; exit 1; }

    echo "==> Guardando commit actual para posible rollback..."
    PREVIOUS_COMMIT=$(git rev-parse HEAD)
    # "HEAD" si el checkout estaba desacoplado: el rollback vuelve al commit sin rama.
    PREVIOUS_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    # DEPLOY_DEPS_FILE y DEPLOY_BACKUP_DIR llegan desde el comando ssh (arriba); el default aplica si vienen vacíos.
    DEPS_ANTERIORES="${DEPLOY_DEPS_FILE:-/tmp/telemetry-deps.txt}"

    echo "==> Respaldando dependencias actuales (para rollback)..."
    install -m 600 /dev/null "$DEPS_ANTERIORES"
    ./.venv/bin/pip freeze > "$DEPS_ANTERIORES"

    # Health-check por HTTP: hasta MAX_WAIT segundos, un intento cada INTERVAL. Devuelve 0 si /health da 200.
    MAX_WAIT=30
    INTERVAL=2
    ATTEMPTS=$((MAX_WAIT / INTERVAL))
    esperar_health() {
        local i HTTP_STATUS
        for i in $(seq 1 "$ATTEMPTS"); do
            sleep "$INTERVAL"
            HTTP_STATUS=$(./.venv/bin/python3 -c "import urllib.request; print(urllib.request.urlopen('$HEALTH_URL', timeout=5).status)" 2>/dev/null || echo "000")
            if [[ "$HTTP_STATUS" == "200" ]]; then
                echo "Health-check OK (HTTP 200) en el intento $i."
                return 0
            fi
            echo "Intento $i/$ATTEMPTS: servicio no responde con HTTP 200 (status: $HTTP_STATUS). Reintentando..."
        done
        return 1
    }

    # Rollback común (#17). Sale SIEMPRE con exit 1: un deploy revertido nunca puede dejar el CD en verde. Si una
    # parte del propio rollback falla, no re-entra ni corta a mitad: hace el resto y avisa "ROLLBACK INCOMPLETO".
    # Si la base ya se detuvo (con_base), después del rollback reinicia el servicio y repite el health-check: un
    # rollback que deja el servicio caído avisa "ROLLBACK FALLIDO" y no "Rollback ejecutado" (#24).
    #   $1: motivo. $2: "con_base" si la base ya pudo cambiar (después del stop) y hay que restaurar el dump.
    abortar_con_rollback() {
        trap - ERR
        set +e
        local completo=true servicio_ok=true
        echo "ERROR: $1"
        if [ "${2:-}" = con_base ]; then
            sudo systemctl stop "$DEPLOY_SERVICE_NAME" || completo=false
            echo "==> Restaurando base desde $BACKUP_FILE..."
            gunzip -c "$BACKUP_FILE" | mysql --defaults-file="$MYCNF" "$DB_NAME" || completo=false
        fi
        echo "==> Rollback de código y dependencias a $PREVIOUS_COMMIT..."
        if [ "$PREVIOUS_BRANCH" = HEAD ]; then
            git checkout -f --detach "$PREVIOUS_COMMIT" || completo=false
        else
            git checkout -f "$PREVIOUS_BRANCH" || completo=false
        fi
        git reset --hard "$PREVIOUS_COMMIT" || completo=false
        ./.venv/bin/pip install -r "$DEPS_ANTERIORES" || completo=false
        if [ "${2:-}" = con_base ]; then
            echo "==> Reiniciando servicio $DEPLOY_SERVICE_NAME tras el rollback..."
            sudo systemctl restart "$DEPLOY_SERVICE_NAME" || completo=false
            echo "==> Verificando salud del servicio tras el rollback ($HEALTH_URL)..."
            esperar_health || servicio_ok=false
        fi
        if [ "$servicio_ok" = false ]; then
            echo "ERROR: ROLLBACK FALLIDO: servicio caído tras el rollback (sin HTTP 200 en ${MAX_WAIT}s). Revisar el VPS a mano."
        elif [ "$completo" = true ]; then
            echo "ERROR: Deploy fallido. Rollback ejecutado${2:+ (base, código y dependencias); el deploy se revirtió y el servicio está OK}."
        else
            echo "ERROR: ROLLBACK INCOMPLETO. Revisar el VPS a mano: servicio, base, código y .venv."
        fi
        exit 1
    }

    # Desde acá hasta el `systemctl stop`, cualquier fallo (git, pip, data/, dump) revierte el código. La base todavía
    # no se tocó y el servicio sigue corriendo con el código anterior cargado en memoria.
    trap 'abortar_con_rollback "falló la línea $LINENO antes de detener el servicio; la base no se tocó."' ERR

    echo "==> Actualizando código (fast-forward only)..."
    if [ -n "${GITHUB_TOKEN:-}" ] && [ -n "${GITHUB_REPOSITORY:-}" ]; then
        AUTH=$(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 -w0)
        # fetch a refs/remotes/origin/main + merge, no `pull <URL> main`: un pull por URL deja origin/main
        # congelado en el VPS y `git status` miente sobre lo desplegado (#16). Mismo token efímero.
        git -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $AUTH" \
            fetch "https://github.com/${GITHUB_REPOSITORY}.git" "$DEPLOY_BRANCH:refs/remotes/origin/$DEPLOY_BRANCH"
        git checkout "$DEPLOY_BRANCH" 2>/dev/null || git checkout -b "$DEPLOY_BRANCH" --track "origin/$DEPLOY_BRANCH"
        git merge --ff-only "origin/$DEPLOY_BRANCH"
    else
        # Sin token no hay fetch explícito: la rama de deploy tiene que existir local con upstream (queda así tras
        # el bootstrap). El checkout la deja como rama actual para que el pull siga su upstream.
        git checkout "$DEPLOY_BRANCH"
        git pull --ff-only
    fi

    echo "==> Instalando dependencias..."
    # Versiones exactas del lockfile (D1), las mismas que probó CI.
    ./.venv/bin/pip install -r requirements.lock

    echo "==> Actualizando datos maestros (repo independiente datamaq-data)..."
    if [ -d "data/.git" ]; then
        git -C data pull --ff-only
        # El `git pull --ff-only` del código (arriba) puede haber borrado archivos de data/ del
        # working tree si datamaq-telemetry todavía los trackeaba en el commit anterior (pasó una
        # vez en la migración a repo independiente, 2026-09-25: el pull del padre eliminó los YAML
        # físicamente y este `pull` del repo anidado, ya al día con el remoto, no los restauró).
        # `checkout -- .` reconcilia el working tree con HEAD sin importar quién borró qué.
        git -C data checkout -- .
    elif [ -d "data" ] && [ -n "$(ls -A data 2>/dev/null)" ]; then
        echo "ADVERTENCIA: data/ existe pero no es un repo git (¿migración no aplicada?). Se omite la actualización."
    else
        git clone git@github.com-datamaq-data:datamaq-automation/datamaq-data.git data
    fi

    echo "==> Detectando cambios TI en configuración (auditoría)..."
    if [ -d "data/.git" ]; then
        if ! ./.venv/bin/python -m scripts.detect_ti_changes; then
            echo "ADVERTENCIA: la detección de cambios TI falló (no bloqueante)."
        fi
    fi

    echo "==> Verificando permisos de lectura del código y datos para el usuario del servicio..."
    # El servicio corre con otro usuario (drop-in user.conf). Solo se normaliza lo que trackea git (código y datos
    # maestros) y sus directorios: .env, backups y lo no trackeado conservan su modo, porque ahí hay credenciales.
    # Va antes del backup y del stop: si algo sigue sin lectura, el rollback de código corre sin tocar la base.
    ancestros_trackeados() {
        git ls-files | awk -F/ 'NF > 1 { p = ""; for (i = 1; i < NF; i++) { p = (p == "" ? $i : p "/" $i); print p } }'
    }
    normalizar_permisos() {
        git ls-files -z | xargs -0 -r chmod o+r -- || true
        { echo .; ancestros_trackeados; } | sort -u | xargs -r -d '\n' chmod o+rx -- || true
    }
    sin_lectura() {
        local ruta
        while IFS= read -r -d '' ruta; do find "$ruta" -maxdepth 0 ! -perm -o=r -print || true; done < <(git ls-files -z)
        while IFS= read -r ruta; do find "$ruta" -maxdepth 0 ! -perm -o=rx -print || true; done < <({ echo .; ancestros_trackeados; } | sort -u)
        return 0
    }
    for raiz in . data; do
        if [ -d "$raiz/.git" ]; then
            (cd "$raiz" && normalizar_permisos)
        fi
    done
    PERMISOS_MALOS=""
    for raiz in . data; do
        if [ -d "$raiz/.git" ]; then
            SIN_LECTURA=$(cd "$raiz" && sin_lectura)
            if [ -n "$SIN_LECTURA" ]; then
                PERMISOS_MALOS+="$(printf '%s\n' "$SIN_LECTURA" | sed "s#^#$raiz/#")"$'\n'
            fi
        fi
    done
    if [ -n "$PERMISOS_MALOS" ]; then
        printf '%s' "$PERMISOS_MALOS"
        abortar_con_rollback "hay archivos o directorios trackeados sin lectura para el usuario del servicio (listados arriba)."
    fi

    echo "==> Backup de la base antes de migrar (D-5)..."
    set +u  # .env es de terceros: no exigirle que no use variables sin definir.
    # shellcheck disable=SC1091
    source .env
    set -u
    : "${DB_HOST:?falta DB_HOST en .env}" "${DB_USER:?falta DB_USER en .env}" "${DB_NAME:?falta DB_NAME en .env}"
    : "${DB_PASSWORD?falta DB_PASSWORD en .env}"
    # Credenciales de la base en un archivo 600 (mktemp lo crea 600 con cualquier umask), no en argv: con -p"$DB_PASSWORD" cualquier usuario local
    # la veía en `ps` mientras corrían mysqldump o mysql (#17). --defaults-file (no -extra-file) para que un
    # ~/.my.cnf del usuario del deploy no pise estos valores; a cambio, no se lee la configuración global de MySQL.
    MYCNF=$(mktemp)
    trap 'rm -f "$MYCNF"' EXIT
    escapar_cnf() { local v=${1//\\/\\\\}; printf '"%s"' "${v//\"/\\\"}"; }
    printf '[client]\nuser=%s\npassword=%s\nhost=%s\n' \
        "$(escapar_cnf "$DB_USER")" "$(escapar_cnf "$DB_PASSWORD")" "$(escapar_cnf "$DB_HOST")" > "$MYCNF"
    BACKUP_DIR="${DEPLOY_BACKUP_DIR:-/tmp/datamaq-telemetry-pre-migracion}"
    # Cada dump es la base completa (usuarios, hashes, tokens OAuth) y el VPS tiene otros usuarios locales (#17).
    # `install -d -m` también corrige el modo de un directorio que ya existía en 755.
    install -d -m 700 "$BACKUP_DIR"
    find "$BACKUP_DIR" -maxdepth 1 -name 'pre_migracion_*.sql.gz' -exec chmod 600 {} +
    BACKUP_FILE="$BACKUP_DIR/pre_migracion_$(date +%Y%m%d_%H%M%S).sql.gz"
    install -m 600 /dev/null "$BACKUP_FILE"
    mysqldump --defaults-file="$MYCNF" --add-drop-table --no-tablespaces "$DB_NAME" | gzip > "$BACKUP_FILE"
    # Un dump vacío o truncado restaurado con --add-drop-table borraría tablas: validar antes de detener nada.
    # `|| true` en el pie: con pipefail, un SIGPIPE de gzip no debe abortar; la integridad ya la probó `gzip -t`.
    PIE_DUMP=""
    if [ -s "$BACKUP_FILE" ] && gzip -t "$BACKUP_FILE"; then
        PIE_DUMP=$(gzip -dc "$BACKUP_FILE" | tail -n 1 || true)
    fi
    case "$PIE_DUMP" in
        *"Dump completed"*) ;;
        *)
            rm -f -- "$BACKUP_FILE"
            abortar_con_rollback "el dump $BACKUP_FILE está vacío, corrupto o incompleto (sin '-- Dump completed')."
            ;;
    esac
    echo "Backup: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
    # Retención corta: solo para el rollback inmediato de este deploy, no reemplaza
    # el backup diario con retención larga fuera del VPS (D-6).
    find "$BACKUP_DIR" -maxdepth 1 -name 'pre_migracion_*.sql.gz' -printf '%T@ %p\n' \
        | sort -rn | tail -n +6 | cut -d' ' -f2- | xargs -r rm --

    # Desde acá la base puede cambiar: los fallos de migración y de health llaman al rollback con la base. Un fallo
    # inesperado de systemctl corta sin rollback, como antes de #17 (ver la spec).
    trap - ERR

    echo "==> Deteniendo servicio antes de migrar (evita escrituras concurrentes durante el ALTER)..."
    sudo systemctl stop "$DEPLOY_SERVICE_NAME"

    echo "==> Aplicando migraciones de base de datos (Alembic)..."
    if ! ./.venv/bin/alembic upgrade head; then
        abortar_con_rollback "la migración falló." con_base
    fi

    echo "==> Iniciando servicio $DEPLOY_SERVICE_NAME..."
    sudo systemctl start "$DEPLOY_SERVICE_NAME"

    echo "==> Verificando salud del servicio vía HTTP ($HEALTH_URL)..."
    if ! esperar_health; then
        abortar_con_rollback "el health-check falló después de ${MAX_WAIT}s." con_base
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

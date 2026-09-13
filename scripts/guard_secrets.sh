#!/usr/bin/env bash
# scripts/guard_secrets.sh — D-2: bloquea que un .env real (o similar) quede trackeado en git.
#
# Origen: scripts/.env.deploy quedó commiteado en eccc85d (2026-09-12) con
# DEPLOY_SSH_USER=root, mezclado en un commit de feature no relacionado. Ese
# archivo pisaba en silencio los secrets de GitHub Actions y tumbó el pipeline
# CD Deploy ~14 horas sin que nadie lo notara. Corre en scripts/pre-push.sh
# (local) y en CI (server-side, no evitable con --no-verify ni desde otra
# máquina sin el hook instalado).
set -eo pipefail

# Cualquier archivo trackeado que "parezca" un .env real: .env, .env.local,
# .env.deploy, etc. — pero NO las plantillas (.example/.sample), que sí
# deben trackearse.
MATCHES="$(git ls-files | grep -E '(^|/)\.env(\.[^.]+)?$' | grep -vE '\.(example|sample)$' || true)"

if [ -n "$MATCHES" ]; then
    echo "❌ Archivo(s) de configuración local trackeados en git (deberían vivir solo en el servidor/máquina local, nunca en el repo):"
    echo "$MATCHES" | sed 's/^/   - /'
    echo
    echo "   Si es un archivo nuevo: sacalo del commit (git rm --cached <archivo>) y agregalo a .gitignore."
    echo "   Si ya necesitás documentar su forma: creá/actualizá <archivo>.example en su lugar."
    exit 1
fi

echo "✓ Sin archivos de configuración local trackeados en git."

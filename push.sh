#!/usr/bin/env bash
# Script integral para hacer git push con Gauntlet local y monitorear el despliegue al VPS en vivo.
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "==> [1/2] Ejecutando Git Push (validando Gauntlet pre-push local)..."
git push "$@"

echo "==> [2/2] Conectando con GitHub Actions para monitorear CI y CD Deploy en vivo..."
python3 scripts/watch_deploy.py

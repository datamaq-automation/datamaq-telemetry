"""Guardas de scripts/deploy-dev.sh (D1): nunca apunta a producción. Se prueban con DEV_DRY_RUN=1,
que valida las guardas e imprime el plan sin abrir SSH."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "deploy-dev.sh"

BASE = {
    "DEV_DRY_RUN": "1",
    "DEV_SSH_HOST": "vps.example",
    "DEV_SSH_USER": "agustin",
    "DEV_SSH_PORT": "22",
}


def _correr(**extra: str) -> subprocess.CompletedProcess[str]:
    entorno = {**os.environ, **BASE, **extra}
    return subprocess.run(["bash", str(SCRIPT)], env=entorno, capture_output=True, text=True, check=False)


def test_destino_dev_valido_pasa_las_guardas() -> None:
    resultado = _correr()
    assert resultado.returncode == 0, resultado.stderr
    assert "guardas OK" in resultado.stdout


def test_rechaza_el_directorio_de_produccion() -> None:
    resultado = _correr(DEV_REMOTE_DIR="/var/www/datamaq-telemetry")
    assert resultado.returncode != 0
    assert "producción" in resultado.stderr


def test_rechaza_el_servicio_de_produccion() -> None:
    resultado = _correr(DEV_SERVICE_NAME="datamaq-telemetry.service")
    assert resultado.returncode != 0
    assert "producción" in resultado.stderr


def test_rechaza_el_puerto_de_produccion_en_el_health() -> None:
    resultado = _correr(DEV_HEALTH_URL="http://127.0.0.1:8885/health")
    assert resultado.returncode != 0
    assert "8885" in resultado.stderr


def test_rechaza_usuario_root() -> None:
    resultado = _correr(DEV_SSH_USER="root")
    assert resultado.returncode != 0
    assert "root" in resultado.stderr


@pytest.mark.parametrize("directorio", ["/var/www/otra-app", "/home/agustin/app"])
def test_rechaza_directorios_fuera_de_datamaq_dev(directorio: str) -> None:
    resultado = _correr(DEV_REMOTE_DIR=directorio)
    assert resultado.returncode != 0
    assert "datamaq-dev" in resultado.stderr

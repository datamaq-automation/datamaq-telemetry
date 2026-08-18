"""Fase 4 — Aprovisionamiento MQTT con credenciales y CA TLS."""

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts import provision_device as pd

RAIZ = Path(__file__).resolve().parents[2]


def _fake_make_request(capturas):
    def fake(url, method="GET", data=None, **kwargs):
        capturas.append((url, data))
        return 200, {}

    return fake


def test_apply_profile_envia_username_y_password(monkeypatch):
    capturas = []
    monkeypatch.setattr(pd, "make_request", _fake_make_request(capturas))

    ok = pd.apply_profile(
        "192.168.4.1",
        "datamaq",
        custom_username="datamaq_device",
        custom_password="secreto123",
    )

    assert ok is True
    post_mqtt = next(d for u, d in capturas if u.endswith("/mqtt_config.json"))
    assert post_mqtt["username"] == "datamaq_device"
    assert post_mqtt["password"] == "secreto123"


def test_apply_profile_ca_file_sobrescribe_ca(monkeypatch, tmp_path):
    pem = tmp_path / "ca.pem"
    pem.write_text(
        "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n",
        encoding="utf-8",
    )
    capturas = []
    monkeypatch.setattr(pd, "make_request", _fake_make_request(capturas))

    pd.apply_profile("192.168.4.1", "datamaq", custom_ca_file=str(pem))

    post_ca = next(d for u, d in capturas if u.endswith("/mqtt_ca_certificate_config.json"))
    assert "AAAA" in post_ca["ca_certificate"]


def test_apply_profile_sin_credenciales_mantiene_perfil(monkeypatch):
    capturas = []
    monkeypatch.setattr(pd, "make_request", _fake_make_request(capturas))

    pd.apply_profile("192.168.4.1", "datamaq")

    post_mqtt = next(d for u, d in capturas if u.endswith("/mqtt_config.json"))
    assert post_mqtt["username"] == ""
    assert post_mqtt["password"] == ""


def test_cli_ayuda_incluye_flags_credenciales():
    cmd = [sys.executable, os.path.join(RAIZ, "scripts", "provision_device.py"), "--help"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0
    assert "--mqtt-username" in result.stdout
    assert "--mqtt-password" in result.stdout
    assert "--mqtt-ca-file" in result.stdout


def test_perfil_datamaq_usa_tls_8883():
    perfil = json.loads((RAIZ / "profiles/datamaq_server.json").read_text(encoding="utf-8"))
    cfg = perfil["mqtt_config"]
    assert cfg["security"] == "TLS-SERVER-AUTH"
    assert cfg["broker_port"] == 8883


def test_perfil_datamaq_sin_secretos_hardcodeados():
    perfil = json.loads((RAIZ / "profiles/datamaq_server.json").read_text(encoding="utf-8"))
    cfg = perfil["mqtt_config"]
    assert cfg["username"] == ""
    assert cfg["password"] == ""

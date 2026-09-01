"""Fase 4 — Aprovisionamiento MQTT con credenciales y CA TLS."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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

    pd.apply_profile(
        "192.168.4.1",
        "datamaq",
        custom_username="datamaq_device",
        custom_password="secreto123",
        custom_ca_file=str(pem),
    )

    post_ca = next(d for u, d in capturas if u.endswith("/mqtt_ca_certificate_config.json"))
    assert "AAAA" in post_ca["ca_certificate"]


def test_apply_profile_sin_credenciales_aborta_sin_escribir(monkeypatch):
    """El broker tiene `allow_anonymous false`: escribir un perfil sin credenciales
    dejaría al medidor sin poder conectar nunca. Debe abortar antes de tocar el equipo."""
    capturas = []
    monkeypatch.setattr(pd, "make_request", _fake_make_request(capturas))

    with pytest.raises(SystemExit) as exc:
        pd.apply_profile("192.168.4.1", "datamaq")

    assert exc.value.code == 1
    assert capturas == []


def test_apply_profile_rechaza_puerto_1883(monkeypatch):
    """El 1883 solo escucha en 127.0.0.1: es inalcanzable desde un medidor."""
    capturas = []
    monkeypatch.setattr(pd, "make_request", _fake_make_request(capturas))

    with pytest.raises(SystemExit):
        pd.apply_profile(
            "192.168.4.1",
            "datamaq",
            custom_port=1883,
            custom_username="datamaq_device",
            custom_password="secreto123",
        )

    assert capturas == []


def test_apply_profile_no_borra_ca_del_equipo(monkeypatch, tmp_path):
    """Un POST de `ca_certificate` vacío borra el CA del medidor y rompe el TLS."""
    perfil_sin_ca = tmp_path / "perfil.json"
    perfil_sin_ca.write_text(
        json.dumps(
            {
                "mqtt_config": {
                    "broker_host": "mqtt.datamaq.com.ar",
                    "broker_port": 8883,
                    "security": "NO-SECURITY",
                    "username": "datamaq_device",
                    "password": "secreto123",
                }
            }
        ),
        encoding="utf-8",
    )
    capturas = []
    monkeypatch.setattr(pd, "make_request", _fake_make_request(capturas))

    # NO-SECURITY sobre 8883 tampoco es válido; se fuerza un modo sin TLS para aislar el caso.
    pd.apply_profile("192.168.4.1", str(perfil_sin_ca), custom_port=1884)

    assert not any(u.endswith("/mqtt_ca_certificate_config.json") for u, _ in capturas)


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
    """El usuario MQTT no es secreto y debe venir fijado; la contraseña nunca se versiona."""
    perfil = json.loads((RAIZ / "profiles/datamaq_server.json").read_text(encoding="utf-8"))
    cfg = perfil["mqtt_config"]
    assert cfg["username"] == "datamaq_device"
    assert cfg["password"] == ""


def test_perfil_datamaq_referencia_ca_existente():
    perfil = json.loads((RAIZ / "profiles/datamaq_server.json").read_text(encoding="utf-8"))
    ca = RAIZ / perfil["mqtt_ca_certificate_file"]
    assert ca.exists(), f"El perfil referencia un CA inexistente: {ca}"
    assert "BEGIN CERTIFICATE" in ca.read_text(encoding="utf-8")


def _fake_lan_config(redes):
    def fake(url, method="GET", data=None, **kwargs):
        assert url.endswith("/lan_config.json")
        return 200, {"wifi_sta": redes}

    return fake


def test_homoglifos_detecta_mu_griega():
    """La MU griega (U+039C) es indistinguible de la M ASCII pero produce otro PSK."""
    mu = chr(0x39C)
    hallazgos = pd._homoglifos(mu + "ABC123")
    assert len(hallazgos) == 1
    pos, nombre, _ = hallazgos[0]
    assert pos == 0
    assert "GREEK" in nombre
    assert pd._homoglifos("ABC123") == []


def test_wifi_audit_rechaza_clave_no_ascii(monkeypatch, capsys):
    mu = chr(0x39C)
    monkeypatch.setattr(
        pd,
        "make_request",
        _fake_lan_config([{"id": 1, "ssid": "MiRed", "password": mu + "iClave123"}]),
    )

    assert pd.auditar_wifi("192.168.4.1", "admin", "powermeter") is False
    salida = capsys.readouterr().out
    assert "NO ASCII" in salida
    assert "GREEK CAPITAL LETTER MU" in salida


def test_wifi_audit_acepta_clave_ascii(monkeypatch):
    monkeypatch.setattr(
        pd,
        "make_request",
        _fake_lan_config([{"id": 1, "ssid": "MiRed", "password": "MiClave123"}]),
    )

    assert pd.auditar_wifi("192.168.4.1", "admin", "powermeter") is True


def test_wifi_audit_sin_redes_configuradas(monkeypatch):
    monkeypatch.setattr(pd, "make_request", _fake_lan_config([{"id": 1, "ssid": "", "password": ""}]))

    assert pd.auditar_wifi("192.168.4.1", "admin", "powermeter") is False

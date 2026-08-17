"""Fase 5 — Gestión de secretos operativos (seed_admin)."""

import pytest

from scripts.seed_admin import construir_parser, obtener_contrasena


def test_seed_admin_rechaza_flag_contrasena():
    parser = construir_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--usuario", "admin", "--contrasena", "secreto"])


def test_seed_admin_lee_contrasena_de_env():
    assert obtener_contrasena({"ADMIN_PASSWORD": "secreto123"}) == "secreto123"


def test_seed_admin_sin_env_usa_getpass(monkeypatch):
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "clave-interactiva")
    assert obtener_contrasena({}) == "clave-interactiva"

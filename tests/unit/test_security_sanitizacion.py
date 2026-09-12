"""tests/unit/test_security_sanitizacion.py — Sanitización de entrada (DTOs y payload MQTT)."""

import pydantic

from src.application.dtos.auth_dto import LoginRequestDTO
from src.application.use_cases.ingestar_telemetria import (
    acotar_payload_bruto,
    sanear_entero,
    sanear_ip,
)


def test_login_dto_rechaza_usuario_largo():
    try:
        LoginRequestDTO(usuario="a" * 129, contrasena="secreto123")
        raise AssertionError("Se esperaba ValidationError")
    except pydantic.ValidationError:
        pass


def test_login_dto_rechaza_contrasena_larga():
    try:
        LoginRequestDTO(usuario="operador@planta.local", contrasena="b" * 129)
        raise AssertionError("Se esperaba ValidationError")
    except pydantic.ValidationError:
        pass


def test_login_dto_acepta_dentro_de_limite():
    dto = LoginRequestDTO(usuario="operador@planta.local", contrasena="c" * 128)
    assert len(dto.contrasena) == 128


def test_ip_invalida_descartada():
    assert sanear_ip("192.168.1.1") == "192.168.1.1"
    assert sanear_ip("no-es-una-ip") is None
    assert sanear_ip(None) is None
    assert sanear_ip(12345) is None


def test_entero_no_numerico_descartado():
    assert sanear_entero("-40") == -40
    assert sanear_entero(42) == 42
    assert sanear_entero("abc") is None
    assert sanear_entero(None) is None
    assert sanear_entero(True) is None


def test_payload_bruto_acotado():
    payload = {"wifi_sta": {"dbm": -40}, "device_info": {"fw": "1.0"}, "secreto": "no-debe-persistir"}
    resultado = acotar_payload_bruto(payload)
    assert set(resultado.keys()) == {"wifi_sta", "device_info"}
    assert resultado["wifi_sta"] == {"dbm": -40}

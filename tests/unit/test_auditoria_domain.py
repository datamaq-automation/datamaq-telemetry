"""tests/unit/test_auditoria_domain.py — Tests unitarios del dominio de auditoría."""

import dataclasses
from datetime import datetime, timezone

import pytest

from src.domain.auditoria.entities import RegistroAuditoria
from src.domain.auditoria.services import SanitizadorAuditoriaService


def test_registro_auditoria_inmutable():
    ahora = datetime.now(timezone.utc)
    registro = RegistroAuditoria(
        id="audit-1",
        registrado_en=ahora,
        categoria="AUTH",
        accion="LOGIN_EXITOSO",
        resultado="EXITO",
        actor_usuario_id="user-123",
        actor_email="admin@datamaq.com",
    )

    assert registro.id == "audit-1"
    assert registro.categoria == "AUTH"
    assert registro.accion == "LOGIN_EXITOSO"
    assert registro.resultado == "EXITO"

    with pytest.raises(dataclasses.FrozenInstanceError):
        registro.resultado = "ERROR"  # type: ignore[misc]


def test_sanitizador_auditoria_redacta_secretos():
    metadatos = {
        "usuario": "operador1",
        "password": "supersecreto123",
        "token": "jwt.abc.xyz",
        "detalle": {
            "totp_secret": "JBSWY3DPEHPK3PXP",
            "motivo": "calibracion",
            "anidado": {
                "api_key": "secret-12345",
                "ok": True,
            },
        },
        "lista": [
            {"contrasena": "clave1"},
            {"normal": "valor"},
        ],
    }

    limpio = SanitizadorAuditoriaService.sanitizar_metadatos(metadatos)
    assert limpio is not None
    assert limpio["usuario"] == "operador1"
    assert limpio["password"] == "[REDACTED]"
    assert limpio["token"] == "[REDACTED]"
    assert limpio["detalle"]["totp_secret"] == "[REDACTED]"
    assert limpio["detalle"]["motivo"] == "calibracion"
    assert limpio["detalle"]["anidado"]["api_key"] == "[REDACTED]"
    assert limpio["detalle"]["anidado"]["ok"] is True
    assert limpio["lista"][0]["contrasena"] == "[REDACTED]"
    assert limpio["lista"][1]["normal"] == "valor"


def test_sanitizador_metadatos_none():
    assert SanitizadorAuditoriaService.sanitizar_metadatos(None) is None

"""tests/unit/test_cambio_contrasena.py — Tests para cambio de contraseña."""

import pytest

from src.application.dtos.cambio_contrasena_dto import (
    ConfirmPasswordChangeRequest,
    ConfirmPasswordChangeResponse,
    RequestPasswordChangeCodeRequest,
    RequestPasswordChangeCodeResponse,
)


def test_solicitar_codigo_request_dto_valido():
    """Validar DTO de solicitud de código."""
    dto = RequestPasswordChangeCodeRequest(password_actual="password123")
    assert dto.password_actual == "password123"


def test_solicitar_codigo_response_dto_valido():
    """Validar DTO de response de código enviado."""
    dto = RequestPasswordChangeCodeResponse(email_destino="user...@example.com")
    assert dto.status == "codigo_enviado"
    assert dto.email_destino == "user...@example.com"


def test_confirmar_cambio_request_dto_valido():
    """Validar DTO de confirmación."""
    dto = ConfirmPasswordChangeRequest(
        codigo="1234", password_nueva="NewPassword123", password_nueva_confirm="NewPassword123"
    )
    assert dto.codigo == "1234"
    assert dto.password_nueva == "NewPassword123"


def test_confirmar_cambio_response_dto_valido():
    """Validar DTO de response de cambio exitoso."""
    dto = ConfirmPasswordChangeResponse(status="cambio_exitoso", mensaje="Contraseña actualizada")
    assert dto.status == "cambio_exitoso"
    assert dto.mensaje == "Contraseña actualizada"


def test_solicitar_codigo_request_rechaza_password_vacia():
    """Validar que password_actual no puede estar vacía."""
    with pytest.raises(ValueError):
        RequestPasswordChangeCodeRequest(password_actual="")


def test_confirmar_cambio_request_rechaza_codigo_invalido():
    """Validar que código debe ser 4 dígitos."""
    with pytest.raises(ValueError):
        ConfirmPasswordChangeRequest(
            codigo="12345",  # 5 dígitos, debe ser 4
            password_nueva="NewPassword123",
            password_nueva_confirm="NewPassword123",
        )


def test_confirmar_cambio_request_rechaza_password_muy_corta():
    """Validar que password_nueva debe tener mínimo 8 caracteres."""
    with pytest.raises(ValueError):
        ConfirmPasswordChangeRequest(codigo="1234", password_nueva="Short1", password_nueva_confirm="Short1")

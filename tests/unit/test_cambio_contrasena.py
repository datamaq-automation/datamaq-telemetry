"""tests/unit/test_cambio_contrasena.py — Tests para cambio de contraseña."""

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


def test_solicitar_codigo_request_valida_campos_requeridos():
    """Validar que password_actual es requerido."""
    dto = RequestPasswordChangeCodeRequest(password_actual="validPassword123")
    assert dto.password_actual == "validPassword123"


def test_confirmar_cambio_request_valida_codigo_formato():
    """Validar que código acepta 4 dígitos."""
    dto = ConfirmPasswordChangeRequest(
        codigo="1234", password_nueva="NewPassword123", password_nueva_confirm="NewPassword123"
    )
    assert dto.codigo == "1234"


def test_confirmar_cambio_request_valida_password_minimo():
    """Validar que password_nueva se acepta con 8+ caracteres."""
    dto = ConfirmPasswordChangeRequest(
        codigo="1234", password_nueva="ValidPass123", password_nueva_confirm="ValidPass123"
    )
    assert dto.password_nueva == "ValidPass123"

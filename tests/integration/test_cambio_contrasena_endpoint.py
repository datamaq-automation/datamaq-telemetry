"""tests/integration/test_cambio_contrasena_endpoint.py — Tests de endpoints de cambio contraseña."""

import pytest


class TestEndpointRequestCode:
    """Tests de PATCH /api/v1/auth/request-password-change-code."""

    def test_usuario_no_autenticado_rechazado(self) -> None:
        """Sin token → 401 Unauthorized."""
        pytest.skip("TODO: Implementar test con cliente no autenticado")

    def test_contrasena_actual_incorrecta_rechazada(self) -> None:
        """Contraseña actual incorrecta → 401."""
        pytest.skip("TODO")

    def test_codigo_generado_y_enviado_por_email(self) -> None:
        """Código OTP generado, enviado por email, código en BD."""
        pytest.skip("TODO")

    def test_response_200_con_email_destino_ofuscado(self) -> None:
        """Response 200: { status: 'codigo_enviado', email_destino: 'agus...@gmail.com' }."""
        pytest.skip("TODO")


class TestEndpointConfirmChange:
    """Tests de PATCH /api/v1/auth/confirm-password-change."""

    def test_usuario_no_autenticado_rechazado(self) -> None:
        """Sin token → 401 Unauthorized."""
        pytest.skip("TODO")

    def test_codigo_invalido_rechazado(self) -> None:
        """Código incorrecto → 400 Bad Request."""
        pytest.skip("TODO")

    def test_contrasena_nueva_validada(self) -> None:
        """Nueva contraseña validada (8+, mayús, dígito)."""
        pytest.skip("TODO")

    def test_cambio_exitoso_invalida_sesiones(self) -> None:
        """Cambio exitoso → todas las sesiones invalidas (menos esta)."""
        pytest.skip("TODO")

    def test_auditoria_registrada_exitosa(self) -> None:
        """Registro en auditoria_cambio_contrasena con estado='cambio_exitoso'."""
        pytest.skip("TODO")

    def test_email_confirmacion_enviado(self) -> None:
        """Email de confirmación enviado (timestamp, IP)."""
        pytest.skip("TODO")

    def test_codigo_consumido_no_reutilizable(self) -> None:
        """Mismo código no se puede usar 2 veces."""
        pytest.skip("TODO")

    def test_response_200_con_mensaje(self) -> None:
        """Response 200: { status: 'cambio_exitoso', mensaje: '...' }."""
        pytest.skip("TODO")

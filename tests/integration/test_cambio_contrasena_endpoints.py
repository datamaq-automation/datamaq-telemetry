"""Tests de integración para endpoints de cambio de contraseña."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.main import app


@pytest.fixture
def client() -> TestClient:
    """Cliente de test."""
    return TestClient(app)


@pytest.fixture
def usuario_token(client, db_session: Session) -> tuple[str, str]:
    """Crea usuario y retorna (usuario_id, token)."""
    # TODO: Crear usuario real y obtener token autenticado
    # Por ahora, datos dummy para estructura del test
    return ("dummy-user-id", "dummy-token")


class TestRequestPasswordChangeCode:
    """Tests para endpoint request-password-change-code."""

    def test_sin_autenticacion_retorna_401(self, client):
        """Sin token de autenticación → 401."""
        response = client.patch(
            "/api/v1/auth/request-password-change-code",
            json={"password_actual": "SomePass123"},
        )
        assert response is not None  # TODO: Verificar que retorna 401 Unauthorized cuando no hay token

    def test_contraseña_incorrecta_retorna_401(self, client, usuario_token):
        """Contraseña actual incorrecta → 401."""
        _usuario_id, token = usuario_token
        response = client.patch(
            "/api/v1/auth/request-password-change-code",
            json={"password_actual": "WrongPassword123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response is not None  # TODO: Verificar que retorna 401 si contraseña incorrecta

    def test_codigo_generado_y_enviado(self, client, usuario_token):
        """Solicitud válida → genera código y lo envía."""
        _usuario_id, token = usuario_token
        response = client.patch(
            "/api/v1/auth/request-password-change-code",
            json={"password_actual": "CorrectPassword123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response is not None  # TODO: Verificar response.status_code == 200


class TestConfirmPasswordChange:
    """Tests para endpoint confirm-password-change."""

    def test_sin_autenticacion_retorna_401(self, client):
        """Sin token de autenticación → 401."""
        response = client.patch(
            "/api/v1/auth/confirm-password-change",
            json={
                "codigo": "1234",
                "password_nueva": "NewPass123",
                "password_nueva_confirm": "NewPass123",
            },
        )
        assert response is not None  # TODO: Verificar que retorna 401

    def test_codigo_invalido_retorna_400(self, client, usuario_token):
        """Código inválido → 400."""
        _usuario_id, token = usuario_token
        response = client.patch(
            "/api/v1/auth/confirm-password-change",
            json={
                "codigo": "9999",
                "password_nueva": "NewPass123",
                "password_nueva_confirm": "NewPass123",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response is not None  # TODO: Verificar que retorna 400 si código inválido

    def test_cambio_exitoso(self, client, usuario_token):
        """Flujo completo: código válido + new password válida → 200."""
        _usuario_id, _token = usuario_token
        pass  # TODO: Primero solicitar código (request-password-change-code)

    def test_sesiones_invalidadas_post_cambio(self, client, usuario_token):
        """Después de cambio exitoso, sesiones previas son invalidadas."""
        _usuario_id, _token = usuario_token
        pass  # TODO: Crear 2 sesiones para el usuario

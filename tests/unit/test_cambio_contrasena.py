"""tests/unit/test_cambio_contrasena.py — Tests unitarios para cambio de contraseña."""

import pytest


class TestValidacionCodigo:
    """Validación de código OTP 4 dígitos."""

    def test_codigo_valido_4_digitos(self) -> None:
        """Código 0000-9999 es válido."""
        pytest.skip("TODO: Implementar lógica de validación código")

    def test_codigo_no_expirado(self) -> None:
        """Código válido si creado_en + 10min > ahora."""
        pytest.skip("TODO")

    def test_codigo_expirado_rechazado(self) -> None:
        """Código rechazado si > 10 min."""
        pytest.skip("TODO")

    def test_codigo_consumido_una_sola_vez(self) -> None:
        """Código consumido → siguiente intento falla."""
        pytest.skip("TODO")


class TestValidacionContrasena:
    """Validación de nueva contraseña."""

    def test_nueva_contrasena_minimo_8_caracteres(self) -> None:
        """Contraseña < 8 char rechazada."""
        pytest.skip("TODO")

    def test_nueva_contrasena_requiere_mayuscula(self) -> None:
        """Contraseña sin mayúscula rechazada."""
        pytest.skip("TODO")

    def test_nueva_contrasena_requiere_digito(self) -> None:
        """Contraseña sin dígito rechazada."""
        pytest.skip("TODO")

    def test_nueva_contrasena_diferente_de_actual(self) -> None:
        """Nueva = actual → rechazada."""
        pytest.skip("TODO")

    def test_confirmacion_debe_coincidir_con_nueva(self) -> None:
        """Nueva ≠ confirmación → rechazada."""
        pytest.skip("TODO")


class TestRateLimit:
    """Rate limiting: máx 5 solicitudes en 10 minutos."""

    def test_primer_codigo_solicitado_ok(self) -> None:
        """Primera solicitud OK."""
        pytest.skip("TODO")

    def test_quinta_solicitud_ok(self) -> None:
        """Quinta solicitud en 10 min OK."""
        pytest.skip("TODO")

    def test_sexta_solicitud_rechazada(self) -> None:
        """Sexta solicitud en 10 min → 429 Too Many Requests."""
        pytest.skip("TODO")

    def test_rate_limit_se_resetea_tras_10_minutos(self) -> None:
        """Pasados 10 min → contador reset."""
        pytest.skip("TODO")

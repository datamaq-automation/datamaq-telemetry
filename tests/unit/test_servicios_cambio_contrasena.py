"""Tests unitarios para servicios de cambio de contraseña."""

from src.domain.usuarios.servicios_contrasena import (
    GeneradorCodigoOTP,
    ServicioTTLValidacion,
    ValidadorContraseña,
)


class TestGeneradorCodigoOTP:
    """Tests para GeneradorCodigoOTP."""

    def test_genera_4_digitos(self):
        """Código generado tiene exactamente 4 dígitos."""
        codigo = GeneradorCodigoOTP.generar()
        assert len(codigo) == 4
        assert codigo.isdigit()

    def test_rango_0000_9999(self):
        """Código está en rango 0000-9999."""
        for _ in range(100):
            codigo = GeneradorCodigoOTP.generar()
            assert 0 <= int(codigo) <= 9999


class TestValidadorContraseña:
    """Tests para ValidadorContraseña."""

    def test_password_valida(self):
        """Contraseña válida pasa validación."""
        es_valida, _ = ValidadorContraseña.validar("MyPassword123")
        assert es_valida

    def test_password_muy_corta(self):
        """Contraseña muy corta falla."""
        es_valida, errores = ValidadorContraseña.validar("Pass1")
        assert not es_valida
        assert any("Mínimo" in e for e in errores)

    def test_password_sin_mayuscula(self):
        """Contraseña sin mayúscula falla."""
        es_valida, errores = ValidadorContraseña.validar("mypassword123")
        assert not es_valida
        assert any("mayúscula" in e for e in errores)

    def test_password_sin_digito(self):
        """Contraseña sin dígito falla."""
        es_valida, errores = ValidadorContraseña.validar("MyPassword")
        assert not es_valida
        assert any("dígito" in e for e in errores)


class TestServicioTTLValidacion:
    """Tests para ServicioTTLValidacion."""

    def test_calcular_expiracion(self):
        """Calcula tiempo de expiración (+10 min desde ahora)."""
        from datetime import datetime, timezone

        ahora = datetime.now(timezone.utc)
        expira = ServicioTTLValidacion.calcular_expiracion()
        # Debe estar dentro de 10-11 minutos en el futuro
        diferencia_segundos = (expira - ahora).total_seconds()
        assert 599 < diferencia_segundos < 601  # ~10 min en segundos

    def test_no_esta_expirado_si_futuro(self):
        """Validación no expirada si TTL es en el futuro."""
        desde_ahora = ServicioTTLValidacion.calcular_expiracion()
        assert not ServicioTTLValidacion.esta_expirado(desde_ahora)

    def test_esta_expirado_si_pasado(self):
        """Validación expirada si TTL es en el pasado."""
        from datetime import datetime, timedelta, timezone

        hace_1_hora = datetime.now(timezone.utc) - timedelta(hours=1)
        assert ServicioTTLValidacion.esta_expirado(hace_1_hora)

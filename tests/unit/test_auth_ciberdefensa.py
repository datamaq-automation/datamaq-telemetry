"""tests/unit/test_auth_ciberdefensa.py."""

import time
from unittest.mock import MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import Response

from src.application.dtos.auth_dto import (
    LoginRequestDTO,
    SolicitarRecuperacionDTO,
)
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.application.use_cases.recuperar_contrasena import (
    SolicitarRecuperacionContrasenaUseCase,
)
from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.exceptions import DemasiadosIntentosError
from src.domain.auth.services import (
    HashContrasenaService,
    RateLimiterService,
    TokenRevocationService,
)
from src.infrastructure.fastapi.security_headers import SecurityHeadersMiddleware
from src.infrastructure.settings.config import Settings


def test_rate_limiter_permite_limite_custom():
    limiter = RateLimiterService(max_intentos=5, ventana_segundos=60)
    for _ in range(2):
        limiter.registrar_intento("k1")

    # Con default (5) todavía permite
    assert limiter.permitir("k1") is True
    # Con limite custom de 2 ya no permite
    assert limiter.permitir("k1", max_intentos=2) is False
    assert limiter.segundos_restantes("k1", max_intentos=2) > 0


def test_recuperacion_rate_limit_por_usuario():
    repo = MagicMock()
    usuario = UsuarioAuth(
        id="u-1",
        usuario="admin@datamaq.com.ar",
        hash_contrasena=HashContrasenaService.generar_hash("clave1234"),
        rol="admin",
        esta_activo=True,
    )
    repo.obtener_por_usuario.return_value = usuario
    token_svc = MagicMock()
    email_svc = MagicMock()
    rate_limiter = RateLimiterService(max_intentos=3, ventana_segundos=900)

    use_case = SolicitarRecuperacionContrasenaUseCase(
        repositorio_usuarios=repo,
        generador_token=token_svc,
        servicio_email=email_svc,
        rate_limiter=rate_limiter,
        max_solicitudes_usuario=3,
        max_solicitudes_ip=10,
    )

    dto = SolicitarRecuperacionDTO(usuario="admin@datamaq.com.ar")

    # 3 solicitudes permitidas
    for _ in range(3):
        res = use_case.ejecutar(dto, clave_ip="192.168.1.50")
        assert res.exito is True

    # 4ta solicitud bloqueada por usuario
    with pytest.raises(DemasiadosIntentosError) as exc:
        use_case.ejecutar(dto, clave_ip="192.168.1.50")
    assert exc.value.retry_after_seg is not None
    assert exc.value.retry_after_seg > 0


def test_recuperacion_rate_limit_por_ip():
    repo = MagicMock()
    repo.obtener_por_usuario.return_value = None  # usuario inexistente igual registra por IP
    token_svc = MagicMock()
    email_svc = MagicMock()
    rate_limiter = RateLimiterService(max_intentos=10, ventana_segundos=900)

    use_case = SolicitarRecuperacionContrasenaUseCase(
        repositorio_usuarios=repo,
        generador_token=token_svc,
        servicio_email=email_svc,
        rate_limiter=rate_limiter,
        max_solicitudes_usuario=5,
        max_solicitudes_ip=3,
    )

    # 3 solicitudes desde la misma IP con diferentes usuarios
    for i in range(3):
        dto = SolicitarRecuperacionDTO(usuario=f"user{i}@datamaq.com.ar")
        res = use_case.ejecutar(dto, clave_ip="10.0.0.99")
        assert res.exito is True

    # 4ta solicitud bloqueada por IP
    dto_nuevo = SolicitarRecuperacionDTO(usuario="otro@datamaq.com.ar")
    with pytest.raises(DemasiadosIntentosError):
        use_case.ejecutar(dto_nuevo, clave_ip="10.0.0.99")


def test_login_password_spraying_bloqueo_por_ip():
    repo = MagicMock()
    repo.obtener_por_usuario.return_value = None  # credenciales invalidas
    hash_svc = HashContrasenaService()
    token_svc = MagicMock()
    rate_limiter = RateLimiterService(max_intentos=5, ventana_segundos=300)

    use_case = AutenticarUsuarioUseCase(
        repo_usuarios=repo,
        hash_service=hash_svc,
        token_service=token_svc,
        minutos_validez=60,
        rate_limiter=rate_limiter,
    )

    # Atacante prueba 20 usuarios diferentes desde la misma IP
    for i in range(20):
        dto = LoginRequestDTO(usuario=f"empleado{i}@datamaq.com.ar", contrasena="Password123!")
        try:
            use_case.login(dto, clave_ip="203.0.113.5")
        except Exception:
            pass

    # Intento 21 debe ser bloqueado por IP
    dto21 = LoginRequestDTO(usuario="victima21@datamaq.com.ar", contrasena="Password123!")
    with pytest.raises(DemasiadosIntentosError) as exc:
        use_case.login(dto21, clave_ip="203.0.113.5")
    assert "IP" in exc.value.mensaje


def test_token_revocation_service():
    revocation = TokenRevocationService()
    ahora_ts = int(time.time())

    # Token emitido a las ahora_ts - 100
    assert revocation.esta_revocado("u-123", iat=ahora_ts - 100) is False

    # Revocamos a u-123 a las ahora_ts - 10
    revocation.revocar_usuario("u-123", timestamp=ahora_ts - 10)

    # Token viejo (iat < revocacion) queda revocado
    assert revocation.esta_revocado("u-123", iat=ahora_ts - 100) is True

    # Token nuevo (iat >= revocacion) es valido
    assert revocation.esta_revocado("u-123", iat=ahora_ts) is False


@pytest.mark.asyncio
async def test_security_headers_middleware_defensivos():
    settings = Settings(
        _env_file=None,
        DEBUG=False,
        API_SECRET_KEY="secreto-fuerte-super-seguro-123456",
        OTP_HMAC_KEY="clave-otp-de-prueba-0123456789",
        DB_PASSWORD="clave-segura",
    )
    app_mock = MagicMock()

    async def mock_call_next(request):
        return Response(content="ok", media_type="application/json")

    middleware = SecurityHeadersMiddleware(app=app_mock, settings=settings)
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/telemetria", "headers": []})
    response = await middleware.dispatch(request, mock_call_next)

    headers = response.headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert "max-age=31536000" in headers["Strict-Transport-Security"]
    assert "camera=()" in headers["Permissions-Policy"]
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert "default-src" in headers["Content-Security-Policy"]

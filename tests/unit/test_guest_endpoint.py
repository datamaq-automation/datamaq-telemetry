"""Endpoint guest (D-04), rate limiting por IP y cabecera Retry-After (D-02)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException, Response

from src.application.dtos.auth_dto import LoginRequestDTO
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.exceptions import CredencialesInvalidasError, DemasiadosIntentosError
from src.domain.auth.ports import RepositorioUsuariosPort
from src.domain.auth.services import HashContrasenaService, RateLimiterService
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi import dependencies as deps
from src.infrastructure.fastapi.error_handler import manejar_error_http
from src.infrastructure.fastapi.routes.auth_router import guest as guest_handler
from src.infrastructure.settings.config import Settings


class _RepoVacio(RepositorioUsuariosPort):
    def obtener_por_usuario(self, usuario: str) -> UsuarioAuth | None:
        return None

    def guardar(self, usuario: UsuarioAuth) -> UsuarioAuth:
        return usuario


class _ClientFake:
    def __init__(self, host: str):
        self.host = host


class _RequestFake:
    def __init__(self, host: str):
        self.client = _ClientFake(host)


def _use_case_guest(rate_limiter: RateLimiterService | None = None) -> AutenticarUsuarioUseCase:
    return AutenticarUsuarioUseCase(
        repo_usuarios=_RepoVacio(),
        hash_service=HashContrasenaService(),
        token_service=JwtTokenService("clave-secreta"),
        minutos_validez=120,
        rate_limiter=rate_limiter,
    )


# G1 — token guest autosuficiente, sin base de datos
def test_guest_genera_token_sin_bd():
    token_service = JwtTokenService("clave-secreta")
    use_case = AutenticarUsuarioUseCase(
        repo_usuarios=_RepoVacio(),
        hash_service=HashContrasenaService(),
        token_service=token_service,
        minutos_validez=120,
    )

    response = use_case.guest("ip:1.2.3.4")

    claims = token_service.verificar(response.token)
    assert claims is not None
    assert claims["sub"] == "invitado"
    assert claims["usuario"] == "invitado"
    assert claims["rol"] == "invitado"
    assert claims["exp"] > datetime.now(timezone.utc).timestamp()


# G2 — handler guest fija la cookie HttpOnly
def test_guest_handler_fija_cookie():
    use_case = _use_case_guest()
    response = Response()
    settings = Settings(_env_file=None, DEBUG=True)

    resultado = guest_handler(_RequestFake("1.2.3.4"), response, use_case, settings)

    assert resultado.token
    set_cookie = response.headers.get("set-cookie", "")
    assert "datamaq_token=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie


# G3 — el token guest es aceptado por get_usuario_actual y /me devuelve invitado
def test_me_con_token_guest(monkeypatch):
    settings = Settings(_env_file=None, AUTH_REQUIRED=True, DEBUG=True, API_SECRET_KEY="s3cr3t0")
    monkeypatch.setattr(deps, "get_settings", lambda: settings)
    service = JwtTokenService("s3cr3t0")
    token = service.generar(
        "invitado",
        "invitado",
        datetime.now(timezone.utc) + timedelta(minutes=30),
        rol="invitado",
    )

    claims = deps.get_usuario_actual(None, token)
    dto = _use_case_guest().me(claims)

    assert dto.usuario == "invitado"
    assert dto.rol == "invitado"


# G4 — rate limiting por IP: 5 sesiones OK, la 6ª bloqueada, otra IP OK
def test_guest_rate_limit_por_ip():
    use_case = _use_case_guest(rate_limiter=RateLimiterService(max_intentos=5, ventana_segundos=300))

    for _ in range(5):
        use_case.guest("ip:1.1.1.1")

    with pytest.raises(DemasiadosIntentosError):
        use_case.guest("ip:1.1.1.1")

    use_case.guest("ip:2.2.2.2")


# G5 — segundos_restantes: 0 si permitido, 1..ventana si bloqueado
def test_rate_limiter_segundos_restantes():
    limiter = RateLimiterService(max_intentos=2, ventana_segundos=60)
    assert limiter.segundos_restantes("u") == 0
    limiter.registrar_intento("u")
    limiter.registrar_intento("u")

    segundos = limiter.segundos_restantes("u")

    assert 1 <= segundos <= 60


# G6 — login bloqueado adjunta retry_after_seg a la excepción
def test_login_bloqueado_adjunta_retry_after():
    use_case = AutenticarUsuarioUseCase(
        repo_usuarios=_RepoVacio(),
        hash_service=HashContrasenaService(),
        token_service=JwtTokenService("clave-secreta"),
        minutos_validez=120,
        rate_limiter=RateLimiterService(max_intentos=1, ventana_segundos=300),
    )

    with pytest.raises(CredencialesInvalidasError):
        use_case.login(LoginRequestDTO(usuario="nadie", contrasena="x"))
    with pytest.raises(DemasiadosIntentosError) as e:
        use_case.login(LoginRequestDTO(usuario="nadie", contrasena="x"))

    assert e.value.retry_after_seg is not None
    assert e.value.retry_after_seg >= 1


# G7 — manejar_error_http emite la cabecera Retry-After en el 429
def test_manejar_error_http_429_con_retry_after():
    with pytest.raises(HTTPException) as e:
        manejar_error_http(DemasiadosIntentosError("Demasiados intentos.", usuario="invitado", retry_after_seg=42))

    assert e.value.status_code == 429
    assert e.value.headers is not None
    assert e.value.headers["Retry-After"] == "42"

"""tests/unit/test_security_auth.py — Autenticación obligatoria, roles y rate limiting."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from src.adapters.presenters.error_presenter import ErrorPresenter
from src.application.dtos.auth_dto import LoginRequestDTO
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.exceptions import DemasiadosIntentosError, NombreUsuarioInvalidoError
from src.domain.auth.ports import RepositorioUsuariosPort
from src.domain.auth.services import HashContrasenaService, RateLimiterService
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi import dependencies as deps
from src.infrastructure.settings.config import Settings


class _RepoUsuarios(RepositorioUsuariosPort):
    def __init__(self, usuario: UsuarioAuth | None = None):
        self.usuario = usuario

    def obtener_por_usuario(self, usuario: str) -> UsuarioAuth | None:
        return self.usuario

    def guardar(self, usuario: UsuarioAuth) -> UsuarioAuth:
        return usuario


class _TokenServiceFake:
    def generar(
        self,
        usuario_id: str,
        usuario: str,
        expira_en: datetime,
        rol: str = "operador",
        organizacion_id: str | None = None,
    ) -> str:
        return f"token-{usuario_id}-{rol}"

    def verificar(self, token: str) -> dict | None:
        return {"sub": "usuario-1", "rol": "operador"}


def _usuario(contrasena: str = "secreto123", rol: str = "operador") -> UsuarioAuth:
    return UsuarioAuth(
        id="usuario-1",
        usuario="operador@planta.local",
        hash_contrasena=HashContrasenaService.generar_hash(contrasena),
        esta_activo=True,
        rol=rol,
    )


# --- RateLimiterService ---


def test_rate_limiter_permite_dentro_de_ventana():
    limiter = RateLimiterService(max_intentos=3, ventana_segundos=60)
    assert limiter.permitir("usuario") is True
    assert limiter.permitir("usuario") is True


def test_rate_limiter_bloquea_tras_exceder():
    limiter = RateLimiterService(max_intentos=2, ventana_segundos=60)
    limiter.registrar_intento("usuario")
    limiter.registrar_intento("usuario")
    assert limiter.permitir("usuario") is False


def test_rate_limiter_reset_tras_login_exitoso():
    limiter = RateLimiterService(max_intentos=2, ventana_segundos=60)
    limiter.registrar_intento("usuario")
    limiter.registrar_intento("usuario")
    limiter.resetear("usuario")
    assert limiter.permitir("usuario") is True


# --- Login con bloqueo ---


def test_login_bloqueado_tras_exceder_intentos():
    repo = _RepoUsuarios(_usuario(contrasena="secreto123"))
    limiter = RateLimiterService(max_intentos=2, ventana_segundos=300)
    use_case = AutenticarUsuarioUseCase(
        repo_usuarios=repo,
        hash_service=HashContrasenaService(),
        token_service=_TokenServiceFake(),
        minutos_validez=120,
        rate_limiter=limiter,
    )

    for _ in range(2):
        try:
            use_case.login(LoginRequestDTO(usuario="operador@planta.local", contrasena="incorrecta"))
            raise AssertionError("Se esperaba CredencialesInvalidasError")
        except Exception as e:
            assert e.__class__.__name__ == "CredencialesInvalidasError"

    try:
        use_case.login(LoginRequestDTO(usuario="operador@planta.local", contrasena="incorrecta"))
        raise AssertionError("Se esperaba DemasiadosIntentosError")
    except DemasiadosIntentosError:
        pass


# --- JWT con rol e iat ---


def test_jwt_incluye_rol_e_iat():
    service = JwtTokenService("clave-secreta")
    expira_en = datetime.now(timezone.utc) + timedelta(minutes=30)
    token = service.generar("usuario-1", "operador@planta.local", expira_en, rol="admin")

    claims = service.verificar(token)

    assert claims is not None
    assert claims["rol"] == "admin"
    assert "iat" in claims


# --- Dependencias de autorización ---


def test_requiere_rol_admin_rechaza_operador():
    try:
        deps.requiere_rol_admin({"rol": "operador"})
        raise AssertionError("Se esperaba HTTPException 403")
    except HTTPException as e:
        assert e.status_code == 403


def test_requiere_rol_admin_acepta_admin():
    claims = deps.requiere_rol_admin({"rol": "admin"})
    assert claims["rol"] == "admin"


def test_get_usuario_actual_anonimo_sin_auth_required(monkeypatch):
    settings = Settings(_env_file=None, AUTH_REQUIRED=False, DEBUG=True, API_SECRET_KEY="s3cr3t0")
    monkeypatch.setattr(deps, "get_settings", lambda: settings)

    claims = deps.get_usuario_actual(None)

    assert claims["sub"] == "anon"
    assert claims["rol"] == "admin"


# --- Presenter 429 ---


def test_error_presenter_mapea_429():
    code, err = ErrorPresenter.presentar_excepcion(DemasiadosIntentosError("bloqueado"))
    assert code == 429
    assert err["mensaje"] == "bloqueado"


def test_error_presenter_mapea_422_nombre_usuario_invalido():
    code, err = ErrorPresenter.presentar_excepcion(NombreUsuarioInvalidoError("vacio"))
    assert code == 422
    assert err["error"] == "ValidationError"
    assert err["mensaje"] == "vacio"


# --- Cookie HttpOnly ---


def test_extraer_token_prioriza_cookie():
    assert deps.extraer_token("cookie-token", "Bearer header-token") == "cookie-token"


def test_extraer_token_fallback_header():
    assert deps.extraer_token(None, "Bearer header-token") == "header-token"


def test_extraer_token_sin_credenciales():
    assert deps.extraer_token(None, None) is None


def test_get_usuario_actual_lee_cookie_valida(monkeypatch):
    settings = Settings(_env_file=None, AUTH_REQUIRED=True, DEBUG=True, API_SECRET_KEY="s3cr3t0")
    monkeypatch.setattr(deps, "get_settings", lambda: settings)
    service = JwtTokenService("s3cr3t0")
    token = service.generar(
        "usuario-1",
        "operador@planta.local",
        datetime.now(timezone.utc) + timedelta(minutes=30),
    )

    claims = deps.get_usuario_actual(None, token)

    assert claims["sub"] == "usuario-1"


def test_get_usuario_actual_sin_cookie_ni_header(monkeypatch):
    settings = Settings(_env_file=None, AUTH_REQUIRED=True, DEBUG=True, API_SECRET_KEY="s3cr3t0")
    monkeypatch.setattr(deps, "get_settings", lambda: settings)

    try:
        deps.get_usuario_actual(None, None)
        raise AssertionError("Se esperaba HTTPException 401")
    except HTTPException as e:
        assert e.status_code == 401
        assert e.detail == "credenciales_invalidas"


def test_token_valido_con_cookie_valida():
    service = JwtTokenService("s3cr3t0")
    token = service.generar(
        "usuario-1",
        "operador@planta.local",
        datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    assert deps.token_valido(token, None, "s3cr3t0") is True


def test_token_valido_rechaza_token_invalido():
    assert deps.token_valido(None, "Bearer falso", "s3cr3t0") is False


def test_token_valido_sin_credenciales():
    assert deps.token_valido(None, None, "s3cr3t0") is False

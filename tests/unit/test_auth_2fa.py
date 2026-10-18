"""tests/unit/test_auth_2fa.py."""

from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from fastapi import Response

from src.application.dtos.auth_dto import (
    Activar2FARequestDTO,
    Desactivar2FARequestDTO,
    LoginRequestDTO,
    Verificar2FARequestDTO,
)
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.application.use_cases.gestionar_2fa import (
    Activar2FAUseCase,
    Desactivar2FAUseCase,
    Setup2FAUseCase,
    Verificar2FAUseCase,
)
from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.exceptions import (
    Codigo2FAInvalidoError,
    CredencialesInvalidasError,
    DemasiadosIntentosError,
    TokenMFAPendienteInvalidoError,
)
from src.domain.auth.ports import RepositorioUsuariosPort
from src.domain.auth.services import CodigosRespaldoService, HashContrasenaService, RateLimiterService
from src.infrastructure.auth.cifrador_2fa import CifradorSecreto2FA
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.auth.totp_service import PyOtpService
from src.infrastructure.fastapi.routes.auth_router import (
    verificar_2fa as verificar_handler,
)
from src.infrastructure.settings.config import get_settings


class MockRepoUsuarios(RepositorioUsuariosPort):
    def __init__(self, usuarios: list[UsuarioAuth] | None = None):
        self.usuarios: dict[str, UsuarioAuth] = {u.usuario: u for u in (usuarios or [])}

    def obtener_por_usuario(self, usuario: str) -> UsuarioAuth | None:
        return self.usuarios.get(usuario)

    def guardar(self, usuario: UsuarioAuth) -> UsuarioAuth:
        self.usuarios[usuario.usuario] = usuario
        return usuario


@pytest.fixture
def cifrador():
    return CifradorSecreto2FA("clave-super-secreta-para-test-12345")


@pytest.fixture
def totp_service():
    return PyOtpService()


@pytest.fixture
def token_service():
    return JwtTokenService("secreto-jwt-para-test-1234567890123")


def test_login_bifurcado_retorna_require_2fa_y_mfa_token(token_service):
    secreto_otp = pyotp.random_base32()
    usuario = UsuarioAuth(
        id="usr-1",
        usuario="admin@datamaq.com",
        hash_contrasena=HashContrasenaService.generar_hash("secreto123"),
        totp_secret=secreto_otp,
        totp_enabled=True,
    )
    repo = MockRepoUsuarios([usuario])
    use_case = AutenticarUsuarioUseCase(
        repo_usuarios=repo,
        hash_service=HashContrasenaService(),
        token_service=token_service,
        minutos_validez=60,
    )

    resp = use_case.login(LoginRequestDTO(usuario="admin@datamaq.com", contrasena="secreto123"))

    assert resp.require_2fa is True
    assert resp.token is None
    assert resp.mfa_token is not None

    claims = token_service.verificar_mfa(resp.mfa_token)
    assert claims is not None
    assert claims["sub"] == "usr-1"
    assert claims["usuario"] == "admin@datamaq.com"
    assert claims["mfa_pending"] is True
    # Un token MFA pendiente no debe ser aceptado por verificar() como sesión completa
    assert token_service.verificar(resp.mfa_token) is None


def test_login_sin_2fa_retorna_require_2fa_false_y_token(token_service):
    usuario = UsuarioAuth(
        id="usr-2",
        usuario="operador@datamaq.com",
        hash_contrasena=HashContrasenaService.generar_hash("secreto123"),
        totp_enabled=False,
    )
    repo = MockRepoUsuarios([usuario])
    use_case = AutenticarUsuarioUseCase(
        repo_usuarios=repo,
        hash_service=HashContrasenaService(),
        token_service=token_service,
        minutos_validez=60,
    )

    resp = use_case.login(LoginRequestDTO(usuario="operador@datamaq.com", contrasena="secreto123"))

    assert resp.require_2fa is False
    assert resp.token is not None
    assert resp.mfa_token is None


def test_verificar_2fa_exitoso_con_totp(token_service, totp_service, cifrador):
    secreto_otp = totp_service.generar_secreto()
    secreto_cifrado = cifrador.cifrar(secreto_otp)
    usuario = UsuarioAuth(
        id="usr-1",
        usuario="admin@datamaq.com",
        hash_contrasena=HashContrasenaService.generar_hash("secreto123"),
        totp_secret=secreto_cifrado,
        totp_enabled=True,
    )
    repo = MockRepoUsuarios([usuario])
    use_case = Verificar2FAUseCase(
        repo_usuarios=repo,
        token_service=token_service,
        totp_service=totp_service,
        cifrador_service=cifrador,
        minutos_validez=60,
    )

    exp_mfa = datetime.now(timezone.utc) + timedelta(minutes=5)
    mfa_token = token_service.generar_mfa(usuario.id, usuario.usuario, exp_mfa)
    codigo_actual = pyotp.TOTP(secreto_otp).now()

    resultado = use_case.verificar(Verificar2FARequestDTO(mfa_token=mfa_token, codigo=codigo_actual))

    assert resultado.token is not None
    assert resultado.require_2fa is False
    claims_sesion = token_service.verificar(resultado.token)
    assert claims_sesion is not None
    assert claims_sesion["usuario"] == "admin@datamaq.com"


def test_verificar_2fa_rechaza_codigo_invalido_y_consume_intento(token_service, totp_service, cifrador):
    secreto_otp = totp_service.generar_secreto()
    usuario = UsuarioAuth(
        id="usr-1",
        usuario="admin@datamaq.com",
        hash_contrasena=HashContrasenaService.generar_hash("secreto123"),
        totp_secret=cifrador.cifrar(secreto_otp),
        totp_enabled=True,
    )
    repo = MockRepoUsuarios([usuario])
    rate_limiter = RateLimiterService(max_intentos=2, ventana_segundos=60)
    use_case = Verificar2FAUseCase(
        repo_usuarios=repo,
        token_service=token_service,
        totp_service=totp_service,
        cifrador_service=cifrador,
        minutos_validez=60,
        rate_limiter=rate_limiter,
    )

    mfa_token = token_service.generar_mfa(
        usuario.id, usuario.usuario, datetime.now(timezone.utc) + timedelta(minutes=5)
    )

    # Primer intento fallido
    with pytest.raises(Codigo2FAInvalidoError):
        use_case.verificar(Verificar2FARequestDTO(mfa_token=mfa_token, codigo="000000"))

    # Segundo intento fallido
    with pytest.raises(Codigo2FAInvalidoError):
        use_case.verificar(Verificar2FARequestDTO(mfa_token=mfa_token, codigo="111111"))

    # Tercer intento bloqueado por rate limiter
    with pytest.raises(DemasiadosIntentosError):
        use_case.verificar(Verificar2FARequestDTO(mfa_token=mfa_token, codigo="222222"))


def test_verificar_2fa_rechaza_token_mfa_invalido_o_expirado(token_service, totp_service, cifrador):
    repo = MockRepoUsuarios([])
    use_case = Verificar2FAUseCase(
        repo_usuarios=repo,
        token_service=token_service,
        totp_service=totp_service,
        cifrador_service=cifrador,
        minutos_validez=60,
    )

    with pytest.raises(TokenMFAPendienteInvalidoError):
        use_case.verificar(Verificar2FARequestDTO(mfa_token="token-invalido-o-expirado", codigo="123456"))


def test_verificar_2fa_codigo_respaldo_exitoso_y_consume_un_solo_uso(token_service, totp_service, cifrador):
    codigos_planos = CodigosRespaldoService.generar_codigos(4)
    codigo_a_usar = codigos_planos[0]
    hashes = [CodigosRespaldoService.hashear(c) for c in codigos_planos]

    secreto_otp = totp_service.generar_secreto()
    usuario = UsuarioAuth(
        id="usr-1",
        usuario="admin@datamaq.com",
        hash_contrasena=HashContrasenaService.generar_hash("secreto123"),
        totp_secret=cifrador.cifrar(secreto_otp),
        totp_enabled=True,
        totp_backup_codes=hashes,
    )
    repo = MockRepoUsuarios([usuario])
    use_case = Verificar2FAUseCase(
        repo_usuarios=repo,
        token_service=token_service,
        totp_service=totp_service,
        cifrador_service=cifrador,
        minutos_validez=60,
    )

    mfa_token = token_service.generar_mfa(
        usuario.id, usuario.usuario, datetime.now(timezone.utc) + timedelta(minutes=5)
    )

    # Uso exitoso del código de respaldo
    resultado = use_case.verificar(Verificar2FARequestDTO(mfa_token=mfa_token, codigo=codigo_a_usar))
    assert resultado.token is not None

    # El código debe haber sido eliminado (deben quedar 3)
    usuario_actualizado = repo.obtener_por_usuario("admin@datamaq.com")
    assert usuario_actualizado is not None
    assert len(usuario_actualizado.totp_backup_codes) == 3

    # Reintentar con el mismo código consumido debe fallar
    mfa_token_nuevo = token_service.generar_mfa(
        usuario.id, usuario.usuario, datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    with pytest.raises(Codigo2FAInvalidoError):
        use_case.verificar(Verificar2FARequestDTO(mfa_token=mfa_token_nuevo, codigo=codigo_a_usar))


def test_setup_2fa_genera_qr_svg_y_uri_otpauth(totp_service):
    usuario = UsuarioAuth(
        id="usr-1",
        usuario="admin@datamaq.com",
        hash_contrasena=HashContrasenaService.generar_hash("secreto123"),
    )
    repo = MockRepoUsuarios([usuario])
    use_case = Setup2FAUseCase(repo_usuarios=repo, totp_service=totp_service)

    setup_dto = use_case.ejecutar("admin@datamaq.com")

    assert len(setup_dto.secret) >= 16
    assert setup_dto.uri.startswith("otpauth://totp/")
    assert "DataMaq" in setup_dto.uri
    assert "<svg" in setup_dto.qr_svg
    assert len(setup_dto.backup_codes) == 8
    assert all("-" in c for c in setup_dto.backup_codes)


def test_activar_2fa_persiste_secreto_cifrado_si_codigo_es_valido(totp_service, cifrador):
    usuario = UsuarioAuth(
        id="usr-1",
        usuario="admin@datamaq.com",
        hash_contrasena=HashContrasenaService.generar_hash("secreto123"),
        totp_enabled=False,
    )
    repo = MockRepoUsuarios([usuario])
    use_case = Activar2FAUseCase(
        repo_usuarios=repo,
        totp_service=totp_service,
        cifrador_service=cifrador,
    )

    secreto = totp_service.generar_secreto()
    codigo_valido = pyotp.TOTP(secreto).now()
    backup_codes = CodigosRespaldoService.generar_codigos(8)

    dto = Activar2FARequestDTO(secret=secreto, codigo=codigo_valido, backup_codes=backup_codes)
    res = use_case.ejecutar("admin@datamaq.com", dto)

    assert res.exito is True
    usuario_db = repo.obtener_por_usuario("admin@datamaq.com")
    assert usuario_db.totp_enabled is True
    assert usuario_db.totp_secret != secreto  # Debe estar cifrado
    assert cifrador.descifrar(usuario_db.totp_secret) == secreto
    assert len(usuario_db.totp_backup_codes) == 8


def test_activar_2fa_rechaza_si_codigo_es_invalido(totp_service, cifrador):
    usuario = UsuarioAuth(
        id="usr-1",
        usuario="admin@datamaq.com",
        hash_contrasena=HashContrasenaService.generar_hash("secreto123"),
    )
    repo = MockRepoUsuarios([usuario])
    use_case = Activar2FAUseCase(
        repo_usuarios=repo,
        totp_service=totp_service,
        cifrador_service=cifrador,
    )

    dto = Activar2FARequestDTO(
        secret=totp_service.generar_secreto(),
        codigo="000000",
        backup_codes=["AAAA-BBBB"],
    )
    with pytest.raises(Codigo2FAInvalidoError):
        use_case.ejecutar("admin@datamaq.com", dto)


def test_desactivar_2fa_exitoso(totp_service, cifrador):
    secreto = totp_service.generar_secreto()
    usuario = UsuarioAuth(
        id="usr-1",
        usuario="admin@datamaq.com",
        hash_contrasena=HashContrasenaService.generar_hash("mi-password-123"),
        totp_secret=cifrador.cifrar(secreto),
        totp_enabled=True,
        totp_backup_codes=["hash1"],
    )
    repo = MockRepoUsuarios([usuario])
    use_case = Desactivar2FAUseCase(
        repo_usuarios=repo,
        hash_service=HashContrasenaService(),
        totp_service=totp_service,
        cifrador_service=cifrador,
    )

    codigo_valido = pyotp.TOTP(secreto).now()
    dto = Desactivar2FARequestDTO(contrasena="mi-password-123", codigo=codigo_valido)
    res = use_case.ejecutar("admin@datamaq.com", dto)

    assert res.exito is True
    usuario_db = repo.obtener_por_usuario("admin@datamaq.com")
    assert usuario_db.totp_enabled is False
    assert usuario_db.totp_secret is None
    assert usuario_db.totp_backup_codes is None


def test_desactivar_2fa_rechaza_contrasena_incorrecta(totp_service, cifrador):
    secreto = totp_service.generar_secreto()
    usuario = UsuarioAuth(
        id="usr-1",
        usuario="admin@datamaq.com",
        hash_contrasena=HashContrasenaService.generar_hash("password-correcta"),
        totp_secret=cifrador.cifrar(secreto),
        totp_enabled=True,
    )
    repo = MockRepoUsuarios([usuario])
    use_case = Desactivar2FAUseCase(
        repo_usuarios=repo,
        hash_service=HashContrasenaService(),
        totp_service=totp_service,
        cifrador_service=cifrador,
    )

    codigo_valido = pyotp.TOTP(secreto).now()
    dto = Desactivar2FARequestDTO(contrasena="password-incorrecta", codigo=codigo_valido)
    with pytest.raises(CredencialesInvalidasError):
        use_case.ejecutar("admin@datamaq.com", dto)


def test_desactivar_2fa_rechaza_codigo_2fa_incorrecto(totp_service, cifrador):
    secreto = totp_service.generar_secreto()
    usuario = UsuarioAuth(
        id="usr-1",
        usuario="admin@datamaq.com",
        hash_contrasena=HashContrasenaService.generar_hash("password-correcta"),
        totp_secret=cifrador.cifrar(secreto),
        totp_enabled=True,
    )
    repo = MockRepoUsuarios([usuario])
    use_case = Desactivar2FAUseCase(
        repo_usuarios=repo,
        hash_service=HashContrasenaService(),
        totp_service=totp_service,
        cifrador_service=cifrador,
    )

    dto = Desactivar2FARequestDTO(contrasena="password-correcta", codigo="999999")
    with pytest.raises(Codigo2FAInvalidoError):
        use_case.ejecutar("admin@datamaq.com", dto)


def test_handlers_http_2fa_flujo_completo(totp_service, cifrador, token_service):
    secreto = totp_service.generar_secreto()
    usuario = UsuarioAuth(
        id="usr-http",
        usuario="super@datamaq.com",
        hash_contrasena=HashContrasenaService.generar_hash("clave123"),
        totp_secret=cifrador.cifrar(secreto),
        totp_enabled=True,
    )
    repo = MockRepoUsuarios([usuario])
    settings = get_settings()

    verif_uc = Verificar2FAUseCase(
        repo_usuarios=repo,
        token_service=token_service,
        totp_service=totp_service,
        cifrador_service=cifrador,
        minutos_validez=60,
    )

    mfa_token = token_service.generar_mfa(
        usuario.id, usuario.usuario, datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    codigo = pyotp.TOTP(secreto).now()

    response = Response()
    res = verificar_handler(
        dto=Verificar2FARequestDTO(mfa_token=mfa_token, codigo=codigo),
        use_case=verif_uc,
        response=response,
        settings=settings,
    )
    assert res.token is not None
    assert "set-cookie" in response.headers


def test_me_retorna_totp_enabled_true_cuando_usuario_lo_tiene_activo(token_service):
    usuario = UsuarioAuth(
        id="usr-totp-1",
        usuario="admin@datamaq.com.ar",
        hash_contrasena=HashContrasenaService.generar_hash("secreto123"),
        rol="superadmin",
        totp_enabled=True,
    )
    repo = MockRepoUsuarios([usuario])
    use_case = AutenticarUsuarioUseCase(
        repo_usuarios=repo,
        hash_service=HashContrasenaService(),
        token_service=token_service,
        minutos_validez=60,
    )

    dto = use_case.me({"sub": "usr-totp-1", "usuario": "admin@datamaq.com.ar", "rol": "superadmin"})
    assert dto.usuario == "admin@datamaq.com.ar"
    assert dto.rol == "superadmin"
    assert dto.totp_enabled is True


def test_me_retorna_totp_enabled_false_cuando_usuario_no_lo_tiene(token_service):
    usuario = UsuarioAuth(
        id="usr-totp-2",
        usuario="operador@datamaq.com.ar",
        hash_contrasena=HashContrasenaService.generar_hash("secreto123"),
        rol="operador",
        totp_enabled=False,
    )
    repo = MockRepoUsuarios([usuario])
    use_case = AutenticarUsuarioUseCase(
        repo_usuarios=repo,
        hash_service=HashContrasenaService(),
        token_service=token_service,
        minutos_validez=60,
    )

    dto = use_case.me({"sub": "usr-totp-2", "usuario": "operador@datamaq.com.ar", "rol": "operador"})
    assert dto.usuario == "operador@datamaq.com.ar"
    assert dto.rol == "operador"
    assert dto.totp_enabled is False

"""tests/unit/test_dispositivos_confiables.py."""
from datetime import datetime, timedelta

import pyotp
import pytest

from src.application.dtos.auth_dto import (
    LoginRequestDTO,
    Verificar2FARequestDTO,
)
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.application.use_cases.gestionar_2fa import Verificar2FAUseCase
from src.application.use_cases.gestionar_dispositivos_confiables import (
    RevocarDispositivosConfiablesUseCase,
)
from src.domain.auth.entities import DispositivoConfiable, UsuarioAuth, ahora_utc
from src.domain.auth.ports import RepositorioDispositivosConfiablesPort, RepositorioUsuariosPort
from src.domain.auth.services import (
    HashContrasenaService,
    TokenDispositivoService,
)
from src.infrastructure.auth.cifrador_2fa import CifradorSecreto2FA
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.auth.totp_service import PyOtpService


class MockRepoUsuarios(RepositorioUsuariosPort):
    def __init__(self, usuarios: list[UsuarioAuth] | None = None):
        self.usuarios: dict[str, UsuarioAuth] = {u.usuario: u for u in (usuarios or [])}

    def obtener_por_usuario(self, usuario: str) -> UsuarioAuth | None:
        return self.usuarios.get(usuario)

    def obtener_por_id(self, usuario_id: str) -> UsuarioAuth | None:
        for u in self.usuarios.values():
            if u.id == usuario_id:
                return u
        return None

    def guardar(self, usuario: UsuarioAuth) -> UsuarioAuth:
        self.usuarios[usuario.usuario] = usuario
        return usuario


class MockRepoDispositivos(RepositorioDispositivosConfiablesPort):
    def __init__(self, dispositivos: list[DispositivoConfiable] | None = None):
        self.dispositivos: dict[str, DispositivoConfiable] = {d.token_hash: d for d in (dispositivos or [])}

    def obtener_por_hash(self, token_hash: str) -> DispositivoConfiable | None:
        return self.dispositivos.get(token_hash)

    def guardar(self, dispositivo: DispositivoConfiable) -> DispositivoConfiable:
        self.dispositivos[dispositivo.token_hash] = dispositivo
        return dispositivo

    def actualizar_acceso(self, id: str, ip: str, ultimo_acceso: datetime) -> None:
        for d in self.dispositivos.values():
            if d.id == id:
                d.ip_origen = ip
                d.ultimo_acceso_en = ultimo_acceso
                break

    def revocar_todos_de_usuario(self, usuario_id: str) -> int:
        count = 0
        for d in self.dispositivos.values():
            if d.usuario_id == usuario_id and not d.revocado:
                d.revocado = True
                count += 1
        return count


@pytest.fixture
def cifrador():
    return CifradorSecreto2FA("supersecretkey_test_1234567890123456789012")


@pytest.fixture
def totp_service():
    return PyOtpService()


@pytest.fixture
def token_service():
    return JwtTokenService("supersecretkey_test_1234567890123456789012")


def test_entidad_dispositivo_confiable_coincidencia_red_y_validez():
    ahora = ahora_utc()
    disp = DispositivoConfiable(
        id="disp-1",
        usuario_id="user-1",
        token_hash="hash123",
        nombre_dispositivo="Firefox en Linux",
        user_agent="Mozilla/5.0",
        ip_origen="192.168.1.50",
        creado_en=ahora,
        ultimo_acceso_en=ahora,
        expira_en=ahora + timedelta(days=30),
        revocado=False,
    )

    # Coincidencia exacta
    assert disp.coincide_red("192.168.1.50") is True
    # Misma subred /24
    assert disp.coincide_red("192.168.1.99") is True
    # Otra subred
    assert disp.coincide_red("192.168.2.50") is False
    # Valido sin revocar y no expirado
    assert disp.es_valido("192.168.1.10", ahora) is True

    # Invalido si expirado
    disp_expirado = DispositivoConfiable(
        id="disp-2",
        usuario_id="user-1",
        token_hash="hash2",
        ip_origen="10.0.0.1",
        expira_en=ahora - timedelta(seconds=1),
    )
    assert disp_expirado.es_valido("10.0.0.1", ahora) is False

    # Invalido si revocado
    disp_revocado = DispositivoConfiable(
        id="disp-3",
        usuario_id="user-1",
        token_hash="hash3",
        ip_origen="10.0.0.1",
        expira_en=ahora + timedelta(days=1),
        revocado=True,
    )
    assert disp_revocado.es_valido("10.0.0.1", ahora) is False


def test_token_dispositivo_service_generar_y_hashear():
    secreto = TokenDispositivoService.generar_secreto()
    assert len(secreto) >= 32
    hash1 = TokenDispositivoService.calcular_hash(secreto)
    assert len(hash1) == 64
    assert TokenDispositivoService.calcular_hash(secreto) == hash1


def test_login_con_2fa_y_dispositivo_confiable_valido_omite_2fa(token_service):
    hash_service = HashContrasenaService()
    contrasena_hash = hash_service.generar_hash("password123")
    usuario = UsuarioAuth(
        id="u-1",
        usuario="operador@madygraf.com",
        hash_contrasena=contrasena_hash,
        totp_enabled=True,
        totp_secret="TESTSECRET",
    )
    repo_usuarios = MockRepoUsuarios([usuario])
    repo_dispositivos = MockRepoDispositivos()

    raw_secret = "dispositivo_secret_seguro_xyz_123"
    token_hash = TokenDispositivoService.calcular_hash(raw_secret)
    ahora = ahora_utc()
    disp = DispositivoConfiable(
        id="d-1",
        usuario_id="u-1",
        token_hash=token_hash,
        ip_origen="192.168.1.100",
        creado_en=ahora,
        ultimo_acceso_en=ahora,
        expira_en=ahora + timedelta(days=30),
        revocado=False,
    )
    repo_dispositivos.guardar(disp)

    use_case = AutenticarUsuarioUseCase(
        repo_usuarios=repo_usuarios,
        hash_service=hash_service,
        token_service=token_service,
        minutos_validez=60,
        repo_dispositivos=repo_dispositivos,
    )

    dto = LoginRequestDTO(usuario="operador@madygraf.com", contrasena="password123")
    resultado = use_case.login(
        dto,
        device_token=raw_secret,
        ip_origen="192.168.1.105",
    )

    assert resultado.require_2fa is False
    assert resultado.token is not None
    assert resultado.mfa_token is None

    disp_actualizado = repo_dispositivos.obtener_por_hash(token_hash)
    assert disp_actualizado is not None
    assert disp_actualizado.ip_origen == "192.168.1.105"


def test_login_con_2fa_dispositivo_invalido_o_diferente_red_exige_2fa(token_service):
    hash_service = HashContrasenaService()
    contrasena_hash = hash_service.generar_hash("password123")
    usuario = UsuarioAuth(
        id="u-1",
        usuario="operador@madygraf.com",
        hash_contrasena=contrasena_hash,
        totp_enabled=True,
        totp_secret="TESTSECRET",
    )
    repo_usuarios = MockRepoUsuarios([usuario])
    repo_dispositivos = MockRepoDispositivos()

    raw_secret = "dispositivo_secret_seguro_xyz_123"
    token_hash = TokenDispositivoService.calcular_hash(raw_secret)
    ahora = ahora_utc()
    disp = DispositivoConfiable(
        id="d-1",
        usuario_id="u-1",
        token_hash=token_hash,
        ip_origen="192.168.1.100",
        creado_en=ahora,
        ultimo_acceso_en=ahora,
        expira_en=ahora + timedelta(days=30),
        revocado=False,
    )
    repo_dispositivos.guardar(disp)

    use_case = AutenticarUsuarioUseCase(
        repo_usuarios=repo_usuarios,
        hash_service=hash_service,
        token_service=token_service,
        minutos_validez=60,
        repo_dispositivos=repo_dispositivos,
    )

    dto = LoginRequestDTO(usuario="operador@madygraf.com", contrasena="password123")

    # Caso 1: Sin cookie -> Exige 2FA
    res1 = use_case.login(dto, device_token=None, ip_origen="192.168.1.100")
    assert res1.require_2fa is True
    assert res1.mfa_token is not None

    # Caso 2: Con cookie pero desde red desconocida -> Exige 2FA
    res2 = use_case.login(dto, device_token=raw_secret, ip_origen="203.0.113.50")
    assert res2.require_2fa is True
    assert res2.mfa_token is not None

    # Caso 3: Token revocado -> Exige 2FA
    disp.revocado = True
    res3 = use_case.login(dto, device_token=raw_secret, ip_origen="192.168.1.100")
    assert res3.require_2fa is True


def test_verificar_2fa_con_recordar_dispositivo(token_service, totp_service, cifrador):
    usuario = UsuarioAuth(
        id="u-1",
        usuario="operador@madygraf.com",
        hash_contrasena="hash",
        totp_enabled=True,
        totp_secret=cifrador.cifrar("JBSWY3DPEHPK3PXP"),
    )
    repo_usuarios = MockRepoUsuarios([usuario])
    repo_dispositivos = MockRepoDispositivos()

    use_case = Verificar2FAUseCase(
        repo_usuarios=repo_usuarios,
        token_service=token_service,
        totp_service=totp_service,
        cifrador_service=cifrador,
        minutos_validez=60,
        repo_dispositivos=repo_dispositivos,
    )

    mfa_token = token_service.generar_mfa("u-1", "operador@madygraf.com", ahora_utc() + timedelta(minutes=5))
    codigo_valido = pyotp.TOTP("JBSWY3DPEHPK3PXP").now()

    dto = Verificar2FARequestDTO(
        mfa_token=mfa_token,
        codigo=codigo_valido,
        recordar_dispositivo=True,
    )

    resultado = use_case.verificar(
        dto,
        ip_origen="192.168.1.50",
        user_agent="Mozilla/5.0 TestBrowser",
        nombre_dispositivo="Test Browser",
    )

    assert resultado.token is not None
    assert resultado.device_trust_token is not None
    hash_guardado = TokenDispositivoService.calcular_hash(resultado.device_trust_token)
    disp = repo_dispositivos.obtener_por_hash(hash_guardado)
    assert disp is not None
    assert disp.usuario_id == "u-1"
    assert disp.ip_origen == "192.168.1.50"
    assert disp.user_agent == "Mozilla/5.0 TestBrowser"
    assert disp.revocado is False


def test_revocar_todos_dispositivos_use_case():
    repo = MockRepoDispositivos()
    ahora = ahora_utc()
    d1 = DispositivoConfiable(
        id="d-1",
        usuario_id="u-1",
        token_hash="hash1",
        expira_en=ahora + timedelta(days=30),
    )
    d2 = DispositivoConfiable(
        id="d-2",
        usuario_id="u-1",
        token_hash="hash2",
        expira_en=ahora + timedelta(days=30),
    )
    d3 = DispositivoConfiable(
        id="d-3",
        usuario_id="u-2",
        token_hash="hash3",
        expira_en=ahora + timedelta(days=30),
    )
    repo.guardar(d1)
    repo.guardar(d2)
    repo.guardar(d3)

    use_case = RevocarDispositivosConfiablesUseCase(repo_dispositivos=repo)
    revocados = use_case.ejecutar(usuario_id="u-1")

    assert revocados == 2
    disp1 = repo.obtener_por_hash("hash1")
    disp2 = repo.obtener_por_hash("hash2")
    disp3 = repo.obtener_por_hash("hash3")
    assert disp1 is not None and disp1.revocado is True
    assert disp2 is not None and disp2.revocado is True
    assert disp3 is not None and disp3.revocado is False

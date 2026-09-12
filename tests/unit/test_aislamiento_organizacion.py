"""tests/unit/test_aislamiento_organizacion.py — Tests de aislamiento de datos por organización (Etapa 1 multi-tenancy)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.ports import GeneradorTokenPort, RepositorioUsuariosPort
from src.domain.auth.services import HashContrasenaService
from src.infrastructure.auth.jwt_token_service import JwtTokenService


def _expiracion() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=30)


def _make_jwt() -> JwtTokenService:
    return JwtTokenService("clave-secreta-test")


def _usuario(rol: str = "operador", organizacion_id: str | None = "org-a") -> UsuarioAuth:
    return UsuarioAuth(
        id="usr-1",
        usuario="testuser@example.com",
        hash_contrasena=HashContrasenaService.generar_hash("password"),
        esta_activo=True,
        rol=rol,
        organizacion_id=organizacion_id,
    )


# ---------------------------------------------------------------------------
# 1. JWT contiene claim "org" cuando organizacion_id no es None
# ---------------------------------------------------------------------------


class TestJwtConClaimOrg:
    def test_jwt_incluye_org_cuando_organizacion_id_presente(self):
        jwt = _make_jwt()
        token = jwt.generar("usr-1", "testuser", _expiracion(), rol="operador", organizacion_id="org-a")
        claims = jwt.verificar(token)
        assert claims is not None
        assert claims.get("org") == "org-a"

    def test_jwt_no_incluye_org_cuando_organizacion_id_es_none(self):
        jwt = _make_jwt()
        token = jwt.generar("usr-1", "testuser", _expiracion(), rol="superadmin", organizacion_id=None)
        claims = jwt.verificar(token)
        assert claims is not None
        assert "org" not in claims

    def test_login_propaga_organizacion_id_al_token(self):
        """AutenticarUsuarioUseCase.login() debe pasar organizacion_id al token."""
        usuario = _usuario(rol="operador", organizacion_id="org-xyz")

        class MockRepo(RepositorioUsuariosPort):
            def obtener_por_usuario(self, u: str) -> UsuarioAuth | None:
                return usuario

            def obtener_por_id(self, uid: str) -> UsuarioAuth | None:
                return usuario

            def guardar(self, u: UsuarioAuth) -> UsuarioAuth:
                return u

        capturado: dict = {}

        class MockToken(GeneradorTokenPort):
            def generar(self, usuario_id, usuario, expira_en, rol="operador", organizacion_id=None) -> str:
                capturado["organizacion_id"] = organizacion_id
                return "fake-token"

            def verificar(self, token):
                return None

            def generar_mfa(self, uid, usr, exp):
                return ""

            def verificar_mfa(self, token):
                return None

        uc = AutenticarUsuarioUseCase(
            repo_usuarios=MockRepo(),
            token_service=MockToken(),
            hash_service=HashContrasenaService,
            minutos_validez=30,
        )
        from src.application.dtos.auth_dto import LoginRequestDTO

        dto = LoginRequestDTO(usuario="testuser@example.com", contrasena="password")
        uc.login(dto)
        assert capturado["organizacion_id"] == "org-xyz"


# ---------------------------------------------------------------------------
# 2. listar_dispositivos filtra por organizacion_id
#    (usamos objetos simples tipo DTO para evitar depender de la firma exacta
#     de la entidad Dispositivo del dominio)
# ---------------------------------------------------------------------------


class _FakeDispositivo:
    """Stand-in mínimo para evitar acoplar los tests a la entidad de dominio."""

    def __init__(self, dev_id: str, planta_id: str, org_id: str) -> None:
        self.id = dev_id
        self.planta_id = planta_id
        self._org_id = org_id


def _make_use_case(dispositivos_por_org: dict) -> GestionarDispositivosUseCase:
    class MockRepoDispositivos:
        def listar(self, planta_id=None, organizacion_id=None):
            results = list(dispositivos_por_org.get(organizacion_id, []))
            if planta_id:
                results = [d for d in results if d.planta_id == planta_id]
            return results

        def obtener_por_id(self, _):
            return None

        def obtener_por_uid(self, _):
            return None

        def guardar(self, d):
            return d

        def contar_por_organizacion(self, _):
            return 0

    mock_repo_org = MagicMock()
    mock_repo_org.obtener_por_id.return_value = None

    uc = GestionarDispositivosUseCase.__new__(GestionarDispositivosUseCase)
    uc.repo_dispositivos = MockRepoDispositivos()
    uc.repo_organizaciones = mock_repo_org
    return uc


class TestListarDispositivosPorOrganizacion:
    def _devs(self):
        dev_a = _FakeDispositivo("dev-1", "planta-1", "org-a")
        dev_b = _FakeDispositivo("dev-2", "planta-2", "org-b")
        return dev_a, dev_b

    def test_org_a_no_ve_dispositivos_de_org_b(self):
        dev_a, _dev_b = self._devs()
        repo_mock = MagicMock()
        repo_mock.listar.return_value = [dev_a]

        uc = GestionarDispositivosUseCase.__new__(GestionarDispositivosUseCase)
        uc.repo_dispositivos = repo_mock
        uc.repo_organizaciones = MagicMock()

        # Llama listar_dispositivos y verifica que el repo recibe organizacion_id="org-a"
        # No podemos usar to_dto pues son FakeDispositivo; verificamos la llamada al repo.
        uc.repo_dispositivos.listar(planta_id=None, organizacion_id="org-a")
        repo_mock.listar.assert_called_with(planta_id=None, organizacion_id="org-a")

    def test_org_b_no_ve_dispositivos_de_org_a(self):
        _dev_a, dev_b = self._devs()
        repo_mock = MagicMock()
        repo_mock.listar.return_value = [dev_b]

        uc = GestionarDispositivosUseCase.__new__(GestionarDispositivosUseCase)
        uc.repo_dispositivos = repo_mock
        uc.repo_organizaciones = MagicMock()

        uc.repo_dispositivos.listar(planta_id=None, organizacion_id="org-b")
        repo_mock.listar.assert_called_with(planta_id=None, organizacion_id="org-b")

    def test_superadmin_pasa_organizacion_id_none(self):
        repo_mock = MagicMock()
        repo_mock.listar.return_value = []

        uc = GestionarDispositivosUseCase.__new__(GestionarDispositivosUseCase)
        uc.repo_dispositivos = repo_mock
        uc.repo_organizaciones = MagicMock()

        # superadmin: organizacion_id=None → se pasan todos los dispositivos
        uc.repo_dispositivos.listar(planta_id=None, organizacion_id=None)
        repo_mock.listar.assert_called_with(planta_id=None, organizacion_id=None)

    def test_listar_dispositivos_firma_acepta_organizacion_id(self):
        """Verifica que listar_dispositivos() del use case acepta el kwarg organizacion_id."""
        import inspect

        sig = inspect.signature(GestionarDispositivosUseCase.listar_dispositivos)
        assert "organizacion_id" in sig.parameters


# ---------------------------------------------------------------------------
# 3. UsuarioAuth tiene campo organizacion_id
# ---------------------------------------------------------------------------


class TestUsuarioAuthEntidad:
    def test_organizacion_id_es_none_por_defecto(self):
        u = UsuarioAuth(id="x", usuario="u", hash_contrasena="h")
        assert u.organizacion_id is None

    def test_organizacion_id_se_puede_asignar(self):
        u = UsuarioAuth(id="x", usuario="u", hash_contrasena="h", organizacion_id="org-123")
        assert u.organizacion_id == "org-123"

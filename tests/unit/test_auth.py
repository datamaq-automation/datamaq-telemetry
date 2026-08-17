"""Pruebas unitarias del dominio, casos de uso y servicios de autenticación."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.application.dtos.auth_dto import LoginRequestDTO
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.application.use_cases.gestionar_usuarios import GestionarUsuariosUseCase
from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.exceptions import CredencialesInvalidasError, UsuarioInactivoError
from src.domain.auth.ports import GeneradorTokenPort, RepositorioUsuariosPort
from src.domain.auth.services import HashContrasenaService, PoliticaExpiracionService
from src.domain.auth.value_objects import NombreUsuario
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.sqlalchemy.models import UserModel
from src.infrastructure.sqlalchemy.mysql_repositories import MySQLUsuariosRepository


class MockRepositorioUsuarios(RepositorioUsuariosPort):
    def __init__(self, usuarios: list[UsuarioAuth] | None = None):
        self.usuarios: list[UsuarioAuth] = usuarios or []

    def obtener_por_usuario(self, usuario: str) -> UsuarioAuth | None:
        for u in self.usuarios:
            if u.usuario == usuario:
                return u
        return None

    def guardar(self, usuario: UsuarioAuth) -> UsuarioAuth:
        self.usuarios.append(usuario)
        return usuario


class MockTokenService(GeneradorTokenPort):
    def __init__(self):
        self.generados = 0

    def generar(self, usuario_id: str, usuario: str, expira_en: datetime) -> str:
        self.generados += 1
        return f"token-{usuario_id}"

    def verificar(self, token: str) -> dict | None:
        return {"sub": token} if token.startswith("token-") else None


def _usuario_activo(
    contrasena: str = "secreto123",
    usuario: str = "operador@planta.local",
    activo: bool = True,
) -> UsuarioAuth:
    return UsuarioAuth(
        id="usuario-1",
        usuario=usuario,
        hash_contrasena=HashContrasenaService.generar_hash(contrasena),
        esta_activo=activo,
    )


def _use_case_login(repo: RepositorioUsuariosPort) -> tuple[AutenticarUsuarioUseCase, MockTokenService]:
    token_service = MockTokenService()
    use_case = AutenticarUsuarioUseCase(
        repo_usuarios=repo,
        hash_service=HashContrasenaService(),
        token_service=token_service,
        minutos_validez=480,
    )
    return use_case, token_service


def test_nombre_usuario_normaliza():
    nombre = NombreUsuario("  Operador@PLANTA.LOCAL  ")
    assert nombre.valor == "operador@planta.local"


def test_hash_scrypt_genera_y_verifica():
    hash_almacenado = HashContrasenaService.generar_hash("secreto123")
    assert HashContrasenaService.verificar("secreto123", hash_almacenado) is True


def test_hash_scrypt_salt_aleatorio():
    hash_a = HashContrasenaService.generar_hash("secreto123")
    hash_b = HashContrasenaService.generar_hash("secreto123")
    assert hash_a != hash_b


def test_hash_scrypt_no_revela_contrasena():
    hash_almacenado = HashContrasenaService.generar_hash("secreto123")
    assert "secreto123" not in hash_almacenado


def test_hash_scrypt_verificar_incorrecta_o_malformado():
    hash_almacenado = HashContrasenaService.generar_hash("secreto123")
    assert HashContrasenaService.verificar("otra-clave", hash_almacenado) is False
    assert HashContrasenaService.verificar("secreto123", "formato-invalido") is False


def test_login_exitoso():
    repo = MockRepositorioUsuarios([_usuario_activo()])
    use_case, token_service = _use_case_login(repo)

    response = use_case.login(LoginRequestDTO(usuario="operador@planta.local", contrasena="secreto123"))

    assert response.token == "token-usuario-1"
    assert token_service.generados == 1
    assert response.expira_en > datetime.now(timezone.utc)


def test_login_usuario_inexistente():
    repo = MockRepositorioUsuarios()
    use_case, _ = _use_case_login(repo)

    try:
        use_case.login(LoginRequestDTO(usuario="nadie@planta.local", contrasena="secreto123"))
        raise AssertionError("Se esperaba CredencialesInvalidasError")
    except CredencialesInvalidasError:
        pass


def test_login_contrasena_incorrecta():
    repo = MockRepositorioUsuarios([_usuario_activo(contrasena="secreto123")])
    use_case, _ = _use_case_login(repo)

    try:
        use_case.login(LoginRequestDTO(usuario="operador@planta.local", contrasena="incorrecta"))
        raise AssertionError("Se esperaba CredencialesInvalidasError")
    except CredencialesInvalidasError:
        pass


def test_login_usuario_inactivo():
    repo = MockRepositorioUsuarios([_usuario_activo(activo=False)])
    use_case, _ = _use_case_login(repo)

    try:
        use_case.login(LoginRequestDTO(usuario="operador@planta.local", contrasena="secreto123"))
        raise AssertionError("Se esperaba UsuarioInactivoError")
    except UsuarioInactivoError:
        pass


def test_jwt_generar_y_verificar():
    service = JwtTokenService("clave-secreta")
    expira_en = datetime.now(timezone.utc) + timedelta(minutes=30)
    token = service.generar("usuario-1", "operador@planta.local", expira_en)

    claims = service.verificar(token)

    assert claims is not None
    assert claims["sub"] == "usuario-1"
    assert claims["usuario"] == "operador@planta.local"
    assert claims["exp"] == int(expira_en.timestamp())


def test_jwt_token_manipulado():
    service = JwtTokenService("clave-secreta")
    expira_en = datetime.now(timezone.utc) + timedelta(minutes=30)
    token = service.generar("usuario-1", "operador@planta.local", expira_en)

    encabezado, cuerpo, _firma = token.split(".")
    manipulando = f"{encabezado}.{cuerpo}.AAAA"

    assert service.verificar(manipulando) is None
    assert service.verificar("token-malformado") is None


def test_jwt_token_expirado():
    service = JwtTokenService("clave-secreta")
    expira_en = datetime.now(timezone.utc) - timedelta(minutes=1)
    token = service.generar("usuario-1", "operador@planta.local", expira_en)

    assert service.verificar(token) is None


def test_politica_expiracion():
    ahora = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)
    assert PoliticaExpiracionService.calcular_expiracion(ahora, 480) == ahora + timedelta(minutes=480)


def test_crear_usuario_idempotente():
    repo = MockRepositorioUsuarios()
    use_case = GestionarUsuariosUseCase(repo, HashContrasenaService())

    primero = use_case.crear_usuario("admin@planta.local", "admin123")
    segundo = use_case.crear_usuario("admin@planta.local", "otra-contrasena")

    assert len(repo.usuarios) == 1
    assert primero.id == segundo.id
    assert primero.hash_contrasena == segundo.hash_contrasena
    assert "admin123" not in primero.hash_contrasena


def test_repositorio_usuarios_sqlite():
    engine = create_engine("sqlite://")
    UserModel.__table__.create(engine)
    session_local = sessionmaker(bind=engine)
    db: Session = session_local()
    try:
        repo = MySQLUsuariosRepository(db)
        usuario = UsuarioAuth(
            id="usuario-1",
            usuario="operador@planta.local",
            hash_contrasena="hash-falso",
            esta_activo=True,
        )

        guardado = repo.guardar(usuario)
        obtenido = repo.obtener_por_usuario("operador@planta.local")

        assert guardado.id == "usuario-1"
        assert obtenido is not None
        assert obtenido.usuario == "operador@planta.local"
        assert obtenido.hash_contrasena == "hash-falso"
        assert repo.obtener_por_usuario("inexistente") is None
    finally:
        db.close()

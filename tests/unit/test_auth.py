"""tests/unit/test_auth.py — Pruebas unitarias del dominio, casos de uso y servicios de autenticación."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from structlog.testing import capture_logs

from src.application.dtos.auth_dto import LoginRequestDTO, MeResponseDTO
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.application.use_cases.gestionar_usuarios import GestionarUsuariosUseCase
from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.exceptions import (
    CredencialesInvalidasError,
    NombreUsuarioInvalidoError,
    UsuarioInactivoError,
)
from src.domain.auth.ports import GeneradorTokenPort, RepositorioUsuariosPort
from src.domain.auth.services import HashContrasenaService, PoliticaExpiracionService
from src.domain.auth.value_objects import NombreUsuario
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.routes.auth_router import login as login_handler
from src.infrastructure.fastapi.routes.auth_router import logout as logout_handler
from src.infrastructure.fastapi.routes.auth_router import me as me_handler
from src.infrastructure.settings.config import get_settings
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

    def obtener_por_id(self, usuario_id: str) -> UsuarioAuth | None:
        for u in self.usuarios:
            if u.id == usuario_id:
                return u
        return None

    def guardar(self, usuario: UsuarioAuth) -> UsuarioAuth:
        self.usuarios.append(usuario)
        return usuario


class MockTokenService(GeneradorTokenPort):
    def __init__(self):
        self.generados = 0

    def generar(
        self,
        usuario_id: str,
        usuario: str,
        expira_en: datetime,
        rol: str = "operador",
        organizacion_id: str | None = None,
    ) -> str:
        self.generados += 1
        return f"token-{usuario_id}"

    def verificar(self, token: str) -> dict | None:
        return {"sub": token} if token.startswith("token-") else None

    def generar_mfa(self, usuario_id: str, usuario: str, expira_en: datetime) -> str:
        return f"mfa-{usuario_id}"

    def verificar_mfa(self, token: str) -> dict | None:
        return (
            {"sub": token.removeprefix("mfa-"), "usuario": token.removeprefix("mfa-"), "mfa_pending": True}
            if token.startswith("mfa-")
            else None
        )

    def generar_recuperacion(self, usuario_id: str, usuario: str, expira_en: datetime, hash_actual: str) -> str:
        return f"reset-{usuario_id}"

    def verificar_recuperacion(self, token: str) -> dict | None:
        return (
            {"sub": token.removeprefix("reset-"), "usuario": token.removeprefix("reset-"), "purpose": "pwd_reset"}
            if token.startswith("reset-")
            else None
        )


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


def test_nombre_usuario_rechaza_no_email():
    with pytest.raises(NombreUsuarioInvalidoError) as exc_info:
        NombreUsuario("admin")
    assert "correo electrónico válido" in str(exc_info.value)


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


# E8 — login fallido adjunta el usuario normalizado a la excepción
def test_login_fallido_lleva_usuario_normalizado():
    repo = MockRepositorioUsuarios()
    use_case, _ = _use_case_login(repo)

    try:
        use_case.login(LoginRequestDTO(usuario="  Operador@Planta.Local  ", contrasena="x"))
        raise AssertionError("Se esperaba CredencialesInvalidasError")
    except CredencialesInvalidasError as e:
        assert e.usuario == "operador@planta.local"


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
    UserModel.metadata.create_all(engine)
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


def test_login_handler_exitoso():
    repo = MockRepositorioUsuarios([_usuario_activo()])
    use_case = AutenticarUsuarioUseCase(repo, HashContrasenaService(), MockTokenService(), 480)

    response = login_handler(
        LoginRequestDTO(usuario="operador@planta.local", contrasena="secreto123"),
        use_case,
        Response(),
        get_settings(),
    )

    assert response.token == "token-usuario-1"


def test_login_handler_credenciales_invalidas():
    repo = MockRepositorioUsuarios()
    use_case = AutenticarUsuarioUseCase(repo, HashContrasenaService(), MockTokenService(), 480)

    try:
        login_handler(
            LoginRequestDTO(usuario="nadie@planta.local", contrasena="x"), use_case, Response(), get_settings()
        )
        raise AssertionError("Se esperaba HTTPException 401")
    except HTTPException as e:
        assert e.status_code == 401
        assert e.detail == "credenciales_invalidas"


def test_login_handler_usuario_inactivo():
    repo = MockRepositorioUsuarios([_usuario_activo(activo=False)])
    use_case = AutenticarUsuarioUseCase(repo, HashContrasenaService(), MockTokenService(), 480)

    try:
        login_handler(
            LoginRequestDTO(usuario="operador@planta.local", contrasena="secreto123"),
            use_case,
            Response(),
            get_settings(),
        )
        raise AssertionError("Se esperaba HTTPException 403")
    except HTTPException as e:
        assert e.status_code == 403
        assert e.detail == "usuario_inactivo"


def test_login_handler_nombre_usuario_invalido():
    repo = MockRepositorioUsuarios()
    use_case = AutenticarUsuarioUseCase(repo, HashContrasenaService(), MockTokenService(), 480)

    try:
        login_handler(LoginRequestDTO(usuario="   ", contrasena="x"), use_case, Response(), get_settings())
        raise AssertionError("Se esperaba HTTPException 422")
    except HTTPException as e:
        assert e.status_code == 422
        assert e.detail == "El nombre de usuario no puede estar vacío."


def test_login_handler_setea_cookie_httponly():
    repo = MockRepositorioUsuarios([_usuario_activo()])
    use_case = AutenticarUsuarioUseCase(repo, HashContrasenaService(), MockTokenService(), 480)
    response = Response()

    login_handler(
        LoginRequestDTO(usuario="operador@planta.local", contrasena="secreto123"),
        use_case,
        response,
        get_settings(),
    )

    set_cookie = response.headers.get("set-cookie", "")
    assert "datamaq_token=token-usuario-1" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie


# E11 — login exitoso emite el evento login_exitoso sin contrasena
def test_login_handler_exitoso_loguea_login_exitoso():
    repo = MockRepositorioUsuarios([_usuario_activo()])
    use_case = AutenticarUsuarioUseCase(repo, HashContrasenaService(), MockTokenService(), 480)

    with capture_logs() as logs:
        login_handler(
            LoginRequestDTO(usuario="operador@planta.local", contrasena="secreto123"),
            use_case,
            Response(),
            get_settings(),
        )

    exitosos = [ev for ev in logs if ev.get("event") == "login_exitoso"]
    assert exitosos, "No se registró el evento login_exitoso"
    assert exitosos[0]["usuario"] == "operador@planta.local"
    assert "contrasena" not in exitosos[0]


def test_logout_borra_cookie():
    response = Response()

    resultado = logout_handler(response, get_settings())

    assert resultado == {"detail": "sesion_cerrada"}
    set_cookie = response.headers.get("set-cookie", "")
    assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie


def test_get_usuario_actual_valido():
    service = JwtTokenService(get_settings().API_SECRET_KEY)
    token = service.generar(
        "usuario-1",
        "operador@planta.local",
        datetime.now(timezone.utc) + timedelta(minutes=30),
    )

    claims = get_usuario_actual(f"Bearer {token}")

    assert claims["sub"] == "usuario-1"
    assert claims["usuario"] == "operador@planta.local"


def test_get_usuario_actual_sin_header():
    try:
        get_usuario_actual(None)
        raise AssertionError("Se esperaba HTTPException 401")
    except HTTPException as e:
        assert e.status_code == 401
        assert e.detail == "credenciales_invalidas"


def test_get_usuario_actual_token_invalido():
    try:
        get_usuario_actual("Bearer token-falso")
        raise AssertionError("Se esperaba HTTPException 401")
    except HTTPException as e:
        assert e.status_code == 401
        assert e.detail == "credenciales_invalidas"


def _use_case_me() -> AutenticarUsuarioUseCase:
    return AutenticarUsuarioUseCase(MockRepositorioUsuarios(), HashContrasenaService(), MockTokenService(), 480)


def test_me_rol_admin():
    dto = _use_case_me().me({"usuario": "operador@planta.local", "rol": "admin"})
    assert isinstance(dto, MeResponseDTO)
    assert dto.usuario == "operador@planta.local"
    assert dto.rol == "admin"


def test_me_roles_operador_y_superadmin():
    use_case = _use_case_me()
    assert use_case.me({"usuario": "u1", "rol": "operador"}).rol == "operador"
    assert use_case.me({"usuario": "u1", "rol": "superadmin"}).rol == "superadmin"


def test_me_rechaza_roles_retirados():
    use_case = _use_case_me()
    for rol in ("invitado", "invitado_global"):
        try:
            use_case.me({"usuario": "u1", "rol": rol})
            raise AssertionError(f"Se esperaba CredencialesInvalidasError para {rol}")
        except CredencialesInvalidasError:
            pass


def test_me_rol_ausente_o_invalido():
    use_case = _use_case_me()
    for claims in ({"usuario": "u1"}, {"usuario": "u1", "rol": "root"}):
        try:
            use_case.me(claims)
            raise AssertionError("Se esperaba CredencialesInvalidasError")
        except CredencialesInvalidasError:
            pass


def test_me_sin_usuario_usa_sub():
    dto = _use_case_me().me({"sub": "anon", "rol": "admin"})
    assert dto.usuario == "anon"
    assert dto.rol == "admin"


def test_me_sin_usuario_ni_sub():
    dto = _use_case_me().me({"rol": "admin"})
    assert dto.usuario == "anon"
    assert dto.rol == "admin"


def test_me_handler_exitoso():
    use_case = _use_case_me()
    dto = me_handler({"usuario": "u1", "rol": "admin"}, use_case)
    assert dto.usuario == "u1"
    assert dto.rol == "admin"


def test_me_handler_rol_invalido():
    use_case = _use_case_me()
    try:
        me_handler({"usuario": "u1", "rol": "root"}, use_case)
        raise AssertionError("Se esperaba HTTPException 401")
    except HTTPException as e:
        assert e.status_code == 401
        assert e.detail == "credenciales_invalidas"

"""tests/unit/test_auth_recuperacion.py — Pruebas unitarias de recuperación y restablecimiento de contraseña vía email."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.application.dtos.auth_dto import (
    RestablecerContrasenaDTO,
    SolicitarRecuperacionDTO,
)
from src.application.use_cases.recuperar_contrasena import (
    RestablecerContrasenaUseCase,
    SolicitarRecuperacionContrasenaUseCase,
)
from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.exceptions import (
    ContrasenaDebilError,
    TokenRecuperacionInvalidoError,
)
from src.domain.auth.ports import (
    RepositorioUsuariosPort,
    ServicioEmailPort,
)
from src.domain.auth.services import HashContrasenaService
from src.infrastructure.auth.email_service import SmtpEmailService
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi.dependencies import (
    get_email_service,
    get_token_service,
    get_usuarios_repository,
)
from src.main import create_app


class MockEmailService(ServicioEmailPort):
    def __init__(self):
        self.enviados: list[tuple[str, str]] = []

    def enviar_email_recuperacion(self, destinatario: str, enlace_restablecimiento: str) -> bool:
        self.enviados.append((destinatario, enlace_restablecimiento))
        return True

    def enviar_codigo_cambio_contrasena(self, destinatario: str, codigo: str) -> bool:
        return True

    def notificar_cambio_contrasena(self, destinatario: str, momento, ip: str | None) -> bool:
        return True


class MockRepoUsuarios(RepositorioUsuariosPort):
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
        for i, u in enumerate(self.usuarios):
            if u.id == usuario.id:
                self.usuarios[i] = usuario
                return usuario
        self.usuarios.append(usuario)
        return usuario


@pytest.fixture
def jwt_service():
    return JwtTokenService("clave-secreta-para-tests-de-recuperacion-123")


@pytest.fixture
def hash_service():
    return HashContrasenaService()


def test_solicitar_recuperacion_usuario_existente(jwt_service):
    repo = MockRepoUsuarios(
        [
            UsuarioAuth(
                id="user-1",
                usuario="operador@datamaq.com.ar",
                hash_contrasena=HashContrasenaService.generar_hash("claveVieja123"),
                esta_activo=True,
            )
        ]
    )
    email_service = MockEmailService()
    use_case = SolicitarRecuperacionContrasenaUseCase(
        repositorio_usuarios=repo,
        generador_token=jwt_service,
        servicio_email=email_service,
        frontend_url="https://app.datamaq.com.ar",
        minutos_expiracion=15,
    )

    resultado = use_case.ejecutar(SolicitarRecuperacionDTO(usuario="operador@datamaq.com.ar"))

    assert resultado.exito is True
    assert "correo con instrucciones" in resultado.mensaje
    assert len(email_service.enviados) == 1
    dest, link = email_service.enviados[0]
    assert dest == "operador@datamaq.com.ar"
    assert "https://app.datamaq.com.ar/restablecer-contrasena?token=" in link


def test_solicitar_recuperacion_usuario_inexistente_anti_enumeracion(jwt_service):
    repo = MockRepoUsuarios([])
    email_service = MockEmailService()
    use_case = SolicitarRecuperacionContrasenaUseCase(
        repositorio_usuarios=repo,
        generador_token=jwt_service,
        servicio_email=email_service,
    )

    resultado = use_case.ejecutar(SolicitarRecuperacionDTO(usuario="fantasma@datamaq.com.ar"))

    assert resultado.exito is True
    assert "correo con instrucciones" in resultado.mensaje
    assert len(email_service.enviados) == 0


def test_solicitar_recuperacion_usuario_inactivo_no_envia(jwt_service):
    repo = MockRepoUsuarios(
        [
            UsuarioAuth(
                id="user-inactivo",
                usuario="bloqueado@datamaq.com.ar",
                hash_contrasena=HashContrasenaService.generar_hash("claveVieja123"),
                esta_activo=False,
            )
        ]
    )
    email_service = MockEmailService()
    use_case = SolicitarRecuperacionContrasenaUseCase(
        repositorio_usuarios=repo,
        generador_token=jwt_service,
        servicio_email=email_service,
    )

    resultado = use_case.ejecutar(SolicitarRecuperacionDTO(usuario="bloqueado@datamaq.com.ar"))

    assert resultado.exito is True
    assert len(email_service.enviados) == 0


def test_restablecer_contrasena_exito(jwt_service, hash_service):
    hash_viejo = HashContrasenaService.generar_hash("claveVieja123")
    usuario = UsuarioAuth(
        id="user-1",
        usuario="admin@datamaq.com.ar",
        hash_contrasena=hash_viejo,
        esta_activo=True,
        totp_enabled=True,
        totp_secret="SECRETO_2FA_EXISTENTE",
    )
    repo = MockRepoUsuarios([usuario])

    ahora = datetime.now(timezone.utc)
    token = jwt_service.generar_recuperacion(
        usuario_id="user-1",
        usuario="admin@datamaq.com.ar",
        expira_en=ahora + timedelta(minutes=15),
        hash_actual=hash_viejo,
    )

    use_case = RestablecerContrasenaUseCase(
        repositorio_usuarios=repo,
        generador_token=jwt_service,
        hash_service=hash_service,
    )

    resultado = use_case.ejecutar(RestablecerContrasenaDTO(token=token, nueva_contrasena="NuevaClaveSuperSegura2026!"))

    assert resultado.exito is True
    assert "actualizada exitosamente" in resultado.mensaje

    # Verificar que el hash se actualizó y valida la nueva clave
    usuario_act = repo.obtener_por_id("user-1")
    assert usuario_act is not None
    assert usuario_act.hash_contrasena != hash_viejo
    assert HashContrasenaService.verificar("NuevaClaveSuperSegura2026!", usuario_act.hash_contrasena) is True
    # Certeza aprobada: 2FA permanece intacto y exigible en el próximo login
    assert usuario_act.totp_enabled is True
    assert usuario_act.totp_secret == "SECRETO_2FA_EXISTENTE"


def test_restablecer_contrasena_un_solo_uso(jwt_service, hash_service):
    hash_viejo = HashContrasenaService.generar_hash("claveVieja123")
    usuario = UsuarioAuth(
        id="user-1",
        usuario="admin@datamaq.com.ar",
        hash_contrasena=hash_viejo,
        esta_activo=True,
    )
    repo = MockRepoUsuarios([usuario])

    token = jwt_service.generar_recuperacion(
        usuario_id="user-1",
        usuario="admin@datamaq.com.ar",
        expira_en=datetime.now(timezone.utc) + timedelta(minutes=15),
        hash_actual=hash_viejo,
    )

    use_case = RestablecerContrasenaUseCase(
        repositorio_usuarios=repo,
        generador_token=jwt_service,
        hash_service=hash_service,
    )

    # Primer uso: OK
    use_case.ejecutar(RestablecerContrasenaDTO(token=token, nueva_contrasena="NuevaClaveValida1!"))

    # Segundo intento con el mismo token: debe fallar por invalidación
    with pytest.raises(TokenRecuperacionInvalidoError) as exc_info:
        use_case.ejecutar(RestablecerContrasenaDTO(token=token, nueva_contrasena="OtraClaveValida2!"))
    assert "ya ha sido utilizado" in str(exc_info.value)


def test_restablecer_contrasena_token_invalido(jwt_service, hash_service):
    repo = MockRepoUsuarios([])
    use_case = RestablecerContrasenaUseCase(
        repositorio_usuarios=repo,
        generador_token=jwt_service,
        hash_service=hash_service,
    )

    with pytest.raises(TokenRecuperacionInvalidoError):
        use_case.ejecutar(RestablecerContrasenaDTO(token="token-falso-invalido", nueva_contrasena="ClaveValida123!"))


def test_restablecer_contrasena_debil(jwt_service, hash_service):
    hash_viejo = HashContrasenaService.generar_hash("claveVieja123")
    usuario = UsuarioAuth(
        id="user-1",
        usuario="admin@datamaq.com.ar",
        hash_contrasena=hash_viejo,
        esta_activo=True,
    )
    repo = MockRepoUsuarios([usuario])

    token = jwt_service.generar_recuperacion(
        usuario_id="user-1",
        usuario="admin@datamaq.com.ar",
        expira_en=datetime.now(timezone.utc) + timedelta(minutes=15),
        hash_actual=hash_viejo,
    )

    use_case = RestablecerContrasenaUseCase(
        repositorio_usuarios=repo,
        generador_token=jwt_service,
        hash_service=hash_service,
    )

    with pytest.raises(ContrasenaDebilError):
        use_case.ejecutar(RestablecerContrasenaDTO(token=token, nueva_contrasena="12345"))


def test_jwt_token_service_aisla_purpose_recuperacion(jwt_service):
    token_recuperacion = jwt_service.generar_recuperacion(
        usuario_id="usr-abc",
        usuario="juan@test.com",
        expira_en=datetime.now(timezone.utc) + timedelta(minutes=15),
        hash_actual="hash123",
    )

    # No debe ser aceptado como token de sesión regular ni MFA
    assert jwt_service.verificar(token_recuperacion) is None
    assert jwt_service.verificar_mfa(token_recuperacion) is None

    # Debe ser aceptado exclusivamente por verificar_recuperacion
    payload = jwt_service.verificar_recuperacion(token_recuperacion)
    assert payload is not None
    assert payload["sub"] == "usr-abc"
    assert payload["purpose"] == "pwd_reset"


def test_smtp_email_service_modo_test():
    service = SmtpEmailService(app_env="test")
    assert service.enviar_email_recuperacion("destinatario@test.com", "https://link-test.com") is True


def test_endpoints_fastapi_recuperacion(jwt_service, hash_service):
    app = create_app()
    client = TestClient(app)

    hash_viejo = HashContrasenaService.generar_hash("antigua123")
    usuario = UsuarioAuth(
        id="user-fastapi",
        usuario="usuario_api@datamaq.com.ar",
        hash_contrasena=hash_viejo,
        esta_activo=True,
    )
    repo = MockRepoUsuarios([usuario])
    email_service = MockEmailService()

    app.dependency_overrides[get_usuarios_repository] = lambda: repo
    app.dependency_overrides[get_email_service] = lambda: email_service
    app.dependency_overrides[get_token_service] = lambda: jwt_service

    # 1. Endpoint solicitar recuperación
    res_sol = client.post(
        "/api/v1/auth/recuperar-contrasena",
        json={"usuario": "usuario_api@datamaq.com.ar"},
    )
    assert res_sol.status_code == 200
    assert len(email_service.enviados) == 1
    _, enlace = email_service.enviados[0]
    token = enlace.split("token=")[1]

    # 2. Endpoint restablecer contraseña exitoso
    res_res = client.post(
        "/api/v1/auth/restablecer-contrasena",
        json={"token": token, "nueva_contrasena": "NuevaClaveFastAPI2026!"},
    )
    assert res_res.status_code == 200
    assert res_res.json()["exito"] is True

    # 3. Endpoint con token ya usado -> 400
    res_reusado = client.post(
        "/api/v1/auth/restablecer-contrasena",
        json={"token": token, "nueva_contrasena": "OtraClaveMas2026!"},
    )
    assert res_reusado.status_code == 400
    assert res_reusado.json()["detail"] == "token_recuperacion_invalido"

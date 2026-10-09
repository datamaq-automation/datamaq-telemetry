"""Endpoints reales de cambio de contraseña autenticado (reemplazan los stubs 501).

App completa con SQLite en memoria, email simulado y clave OTP fija. Cubre 200, 400, 401, 422 y 429.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.domain.auth.services import HashContrasenaService
from src.infrastructure.fastapi.dependencies import get_email_service, get_settings_dep, get_usuario_actual
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import Settings
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.models import Base, CambioContraseniaValidacionModel, UserModel

PASSWORD_ACTUAL = "ActualPass1"
PASSWORD_NUEVA = "NuevaPass22"
CLAVE_OTP = "clave-otp-de-prueba-0123456789"
CLAIMS = {"sub": "u-1", "email": "operador@example.com", "rol": "operador", "org": "org-a"}


@dataclass
class EmailSimulado:
    codigos: list[tuple[str, str]] = field(default_factory=list)

    def enviar_codigo_cambio_contrasena(self, destinatario: str, codigo: str) -> bool:
        self.codigos.append((destinatario, codigo))
        return True

    def notificar_cambio_contrasena(self, destinatario, momento, ip) -> bool:
        return True

    def enviar_email_recuperacion(self, destinatario, enlace) -> bool:
        return True


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(
        UserModel(
            id="u-1",
            username="operador@example.com",
            password_hash=HashContrasenaService.generar_hash(PASSWORD_ACTUAL),
            role="operador",
        )
    )
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def email() -> EmailSimulado:
    return EmailSimulado()


@pytest.fixture()
def cliente(db: Session, email: EmailSimulado) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_email_service] = lambda: email
    app.dependency_overrides[get_usuario_actual] = lambda: CLAIMS
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        _env_file=None, APP_ENV="development", DEBUG=True, OTP_HMAC_KEY=CLAVE_OTP
    )
    return TestClient(app)


def _solicitar(cliente: TestClient, password: str = PASSWORD_ACTUAL):
    return cliente.patch("/api/v1/auth/request-password-change-code", json={"password_actual": password})


def _confirmar(cliente: TestClient, codigo: str, nueva: str = PASSWORD_NUEVA, confirm: str | None = None):
    return cliente.patch(
        "/api/v1/auth/confirm-password-change",
        json={"codigo": codigo, "password_nueva": nueva, "password_nueva_confirm": confirm or nueva},
    )


def test_solicitar_responde_200_con_email_ofuscado_y_envia_codigo(cliente, email):
    respuesta = _solicitar(cliente)
    assert respuesta.status_code == 200
    assert respuesta.json()["email_destino"] == "ope...@example.com"
    assert len(email.codigos) == 1
    assert len(email.codigos[0][1]) == 4 and email.codigos[0][1].isdigit()


def test_solicitar_con_password_incorrecta_responde_401_y_no_envia(cliente, email):
    respuesta = _solicitar(cliente, password="Incorrecta1")
    assert respuesta.status_code == 401
    assert email.codigos == []


def test_sexta_solicitud_en_diez_minutos_responde_429(cliente):
    for _ in range(5):
        assert _solicitar(cliente).status_code == 200
    assert _solicitar(cliente).status_code == 429


def test_solicitar_sin_autenticacion_responde_401(db, email):
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_email_service] = lambda: email
    sin_token = TestClient(app)
    respuesta = sin_token.patch("/api/v1/auth/request-password-change-code", json={"password_actual": PASSWORD_ACTUAL})
    assert respuesta.status_code == 401


def test_confirmar_con_codigo_erroneo_responde_400(cliente, email):
    _solicitar(cliente)
    respuesta = _confirmar(cliente, codigo="0000" if email.codigos[0][1] != "0000" else "1111")
    assert respuesta.status_code == 400


def test_confirmar_sin_codigo_vigente_responde_400(cliente):
    assert _confirmar(cliente, codigo="1234").status_code == 400


def test_confirmar_con_codigo_mal_formado_responde_422(cliente):
    assert _confirmar(cliente, codigo="12a4").status_code == 422
    assert _confirmar(cliente, codigo="123").status_code == 422


def test_confirmar_con_contrasenas_distintas_responde_422(cliente, email):
    _solicitar(cliente)
    respuesta = _confirmar(cliente, codigo=email.codigos[0][1], nueva=PASSWORD_NUEVA, confirm="OtraPass33")
    assert respuesta.status_code == 422


def test_confirmar_con_codigo_correcto_responde_200_y_cambia_contrasena(cliente, email, db):
    _solicitar(cliente)
    respuesta = _confirmar(cliente, codigo=email.codigos[0][1])
    assert respuesta.status_code == 200
    assert respuesta.json()["status"] == "cambio_exitoso"
    usuario = db.get(UserModel, "u-1")
    db.refresh(usuario)
    assert HashContrasenaService.verificar(PASSWORD_NUEVA, usuario.password_hash)
    assert usuario.sesiones_revocadas_antes_de is not None


def test_codigo_ya_usado_no_sirve_de_nuevo(cliente, email):
    _solicitar(cliente)
    codigo = email.codigos[0][1]
    assert _confirmar(cliente, codigo=codigo).status_code == 200
    assert _confirmar(cliente, codigo=codigo, nueva="OtraPass33").status_code == 400


def test_base_guarda_solo_el_hash_del_codigo(cliente, email, db):
    _solicitar(cliente)
    fila = db.query(CambioContraseniaValidacionModel).one()
    assert email.codigos[0][1] not in fila.codigo_hash
    assert len(fila.codigo_hash) == 64


@pytest.mark.parametrize(
    "ruta",
    ["/api/v1/auth/request-password-change-code", "/api/v1/auth/confirm-password-change"],
)
def test_sin_clave_otp_en_produccion_responde_503_sin_tocar_nada(db, email, ruta):
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_email_service] = lambda: email
    app.dependency_overrides[get_usuario_actual] = lambda: CLAIMS
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        _env_file=None,
        APP_ENV="production",
        DEBUG=False,
        API_SECRET_KEY="secreto-fuerte-123456",
        DB_PASSWORD="clave-segura",
    )
    cliente_prod = TestClient(app)

    respuesta = cliente_prod.patch(
        ruta,
        json={
            "password_actual": PASSWORD_ACTUAL,
            "codigo": "1234",
            "password_nueva": PASSWORD_NUEVA,
            "password_nueva_confirm": PASSWORD_NUEVA,
        },
    )

    assert respuesta.status_code == 503
    assert email.codigos == []
    assert db.query(CambioContraseniaValidacionModel).count() == 0

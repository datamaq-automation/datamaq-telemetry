"""tests/unit/test_oauth_secuestro_cliente.py — Issue datamaq#131: el cliente OAuth `claude-ai` no se puede secuestrar.

Un llamador anónimo registraba una redirect_uri propia que contuviera «claude.ai» y la agregaba al cliente legítimo
`claude-ai`; cuando una víctima aprobaba el consentimiento, el código de autorización llegaba al atacante y lo canjeaba
por un token con el rol completo de la víctima. Routers, casos de uso, repositorio OAuth y servicio JWT reales sobre
SQLite en memoria; solo el repositorio de usuarios es un doble y la víctima ya autenticada se simula con claims.
"""

import base64
import hashlib
from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.domain.auth.entities import UsuarioAuth
from src.domain.oauth.services import URIS_REDIRECT_CLAUDE_POR_DEFECTO
from src.infrastructure.fastapi.dependencies import get_usuario_actual, get_usuarios_repository
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.models import Base, OAuthClientModel

# Una de las cuatro URIs oficiales sembradas en CLIENTES_PREDETERMINADOS (oauth_repository.py) y usadas en test_oauth_api.py.
URI_OFICIAL = "https://claude.ai/api/mcp/oauth_callback"
URI_ATACANTE = "https://evil.example/cb?src=claude.ai"
VERIFICADOR = "v" * 64
DESAFIO = base64.urlsafe_b64encode(hashlib.sha256(VERIFICADOR.encode()).digest()).decode().rstrip("=")
VICTIMA = {"sub": "u-victima", "usuario": "gerente@org-v", "rol": "operador", "org": "org-v"}


class _RepoUsuarios:
    def __init__(self, usuarios: list[UsuarioAuth]) -> None:
        self.u = {x.id: x for x in usuarios}

    def obtener_por_id(self, usuario_id):
        return self.u.get(usuario_id)

    def obtener_por_usuario(self, nombre):
        return next((x for x in self.u.values() if x.usuario == nombre), None)

    def guardar(self, usuario):
        self.u[usuario.id] = usuario
        return usuario


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def cliente(db: Session) -> TestClient:
    victima = UsuarioAuth(
        id="u-victima", usuario="gerente@org-v", hash_contrasena="x", rol="admin", organizacion_id="org-v"
    )
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_usuarios_repository] = lambda: _RepoUsuarios([victima])
    app.dependency_overrides[get_usuario_actual] = lambda: VICTIMA
    return TestClient(app)


def _registrar(c: TestClient, uris: list[str], nombre: str = "Claude"):
    return c.post("/oauth/register", json={"client_name": nombre, "redirect_uris": uris})


def _autorizar(c: TestClient, redirect_uri: str, state: str | None = "s", client_id: str = "claude-ai"):
    cuerpo = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": DESAFIO,
        "code_challenge_method": "S256",
        "scope": "read:telemetria",
    }
    if state is not None:
        cuerpo["state"] = state
    return c.post("/api/v1/oauth/authorize", json=cuerpo)


def test_registro_con_uri_ajena_no_obtiene_el_client_id_fijo(cliente):
    _registrar(cliente, [URI_OFICIAL])

    r = _registrar(cliente, [URI_ATACANTE], "Claude (Anthropic)")

    assert r.json()["client_id"] != "claude-ai"
    assert r.json()["client_id"].startswith("dyn-")


def test_registro_con_uri_ajena_no_amplia_las_uris_del_cliente_claude(cliente, db):
    _registrar(cliente, [URI_OFICIAL])
    _registrar(cliente, [URI_ATACANTE], "Claude (Anthropic)")

    fila = db.query(OAuthClientModel).filter_by(client_id="claude-ai").one()

    assert URI_ATACANTE not in fila.redirect_uris.split(",")
    assert set(fila.redirect_uris.split(",")) == set(URIS_REDIRECT_CLAUDE_POR_DEFECTO)


def test_autorizar_rechaza_una_redirect_uri_ajena_para_claude(cliente):
    _registrar(cliente, [URI_OFICIAL])
    _registrar(cliente, [URI_ATACANTE], "Claude (Anthropic)")

    r = _autorizar(cliente, URI_ATACANTE)

    assert r.status_code == 400
    assert r.json()["error"] == "invalid_request"


def test_autorizar_rechaza_una_uri_que_solo_extiende_por_prefijo_a_la_oficial(cliente):
    _registrar(cliente, [URI_OFICIAL])

    r = _autorizar(cliente, URI_OFICIAL + ".evil.test/x")

    assert r.status_code == 400


def test_autorizar_rechaza_la_uri_ajena_aunque_la_fila_ya_este_envenenada(cliente, db):
    """Estado posible en producción: el cliente guardado ya tiene la URI del atacante."""
    db.add(OAuthClientModel(client_id="claude-ai", client_name="Claude", redirect_uris=f"{URI_OFICIAL},{URI_ATACANTE}"))
    db.commit()

    r = _autorizar(cliente, URI_ATACANTE)

    assert r.status_code == 400


def test_cancelar_el_consentimiento_no_redirige_a_una_uri_no_registrada(cliente):
    _registrar(cliente, [URI_OFICIAL])

    r = cliente.post(
        "/api/v1/oauth/consent",
        json={
            "client_id": "claude-ai",
            "redirect_uri": "https://evil.example/phishing",
            "code_challenge": DESAFIO,
            "code_challenge_method": "S256",
            "aprobado": False,
        },
    )

    assert "evil.example" not in r.text


def test_el_state_se_codifica_y_no_inyecta_parametros(cliente):
    _registrar(cliente, [URI_OFICIAL])

    r = _autorizar(cliente, URI_OFICIAL, state="x&code=robado")

    consulta = parse_qs(urlparse(r.json()["redirect_uri"]).query)
    assert len(consulta["code"]) == 1
    assert consulta["state"] == ["x&code=robado"]


def test_el_registro_oficial_de_claude_es_idempotente(cliente, db):
    primero = _registrar(cliente, [URI_OFICIAL]).json()["client_id"]
    segundo = _registrar(cliente, [URI_OFICIAL]).json()["client_id"]

    assert primero == segundo == "claude-ai"
    fila = db.query(OAuthClientModel).filter_by(client_id="claude-ai").one()
    assert set(fila.redirect_uris.split(",")) == set(URIS_REDIRECT_CLAUDE_POR_DEFECTO)


def test_el_flujo_legitimo_de_claude_sigue_funcionando(cliente):
    _registrar(cliente, [URI_OFICIAL])
    autorizacion = _autorizar(cliente, URI_OFICIAL)
    assert autorizacion.status_code == 200
    codigo = parse_qs(urlparse(autorizacion.json()["redirect_uri"]).query)["code"][0]

    r = cliente.post(
        "/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": codigo,
            "code_verifier": VERIFICADOR,
            "redirect_uri": URI_OFICIAL,
            "client_id": "claude-ai",
        },
    )

    assert r.status_code == 200
    assert r.json()["refresh_token"]

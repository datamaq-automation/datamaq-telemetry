from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.application.use_cases.consultar_documentacion_sge import (
    ConsultarDocumentacionSgeUseCase,
)
from src.domain.sge.entities import ArticuloSge
from src.domain.sge.exceptions import (
    RolNoAutorizadoParaPrevisualizacionError,
)
from src.domain.sge.ports import RepositorioDocumentacionSgePort
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import get_settings


class FakeSgeRepository(RepositorioDocumentacionSgePort):
    def __init__(self, articulos: list[ArticuloSge]):
        self._articulos = {a.id: a for a in articulos}

    def listar_todos(self) -> list[ArticuloSge]:
        return list(self._articulos.values())

    def listar_por_rol(self, rol: str) -> list[ArticuloSge]:
        return [a for a in self._articulos.values() if a.es_visible_para(rol)]

    def obtener_por_id(self, articulo_id: str) -> ArticuloSge | None:
        return self._articulos.get(articulo_id)


@pytest.fixture
def articulos_muestra() -> list[ArticuloSge]:
    return [
        ArticuloSge(
            id="sge-op-01",
            titulo="Procedimiento Operativo: Paradas Operativas y Horario Pico",
            categoria="operacion",
            roles_permitidos=("operador", "mantenimiento"),
            resumen="Instrucciones de apagado secuencial para evitar demanda máxima...",
            puntos_clave=(
                "Escalonamiento de arranque de grandes motores",
                "Monitoreo de potencia activa instantánea en TGBT",
            ),
            acciones_inmediatas=("No encender dos compresores simultáneos en horario pico (18 a 23 hs)",),
            referencia_iso="Cláusula 8.1 - Planificación y Control Operativo",
            documento_url="/archivos/sge/IT-EN-03.pdf",
        ),
        ArticuloSge(
            id="sge-mto-01",
            titulo="Mantenimiento Preventivo: Compensación de Reactiva",
            categoria="mantenimiento",
            roles_permitidos=("mantenimiento", "ingeniero"),
            resumen="Protocolo de inspección del banco de capacitores.",
            puntos_clave=("Termografía de pasos",),
            acciones_inmediatas=("Desconectar paso desequilibrado",),
            referencia_iso="Cláusula 8.1",
            documento_url="/archivos/sge/IT-MTO-04.pdf",
        ),
        ArticuloSge(
            id="sge-pol-01",
            titulo="Política Energética",
            categoria="politica",
            roles_permitidos=("operador", "mantenimiento", "ingeniero", "admin"),
            resumen="Política energética general de la organización.",
            puntos_clave=("Eficiencia continua",),
            acciones_inmediatas=("Reportar desvíos",),
            referencia_iso="Cláusula 5.2",
            documento_url=None,
        ),
    ]


# --- Tests de Dominio ---


def test_articulo_sge_inmutabilidad_y_visibilidad(articulos_muestra):
    op = articulos_muestra[0]
    assert op.id == "sge-op-01"
    assert op.categoria == "operacion"
    assert op.es_visible_para("operador") is True
    assert op.es_visible_para("OPERADOR") is True
    assert op.es_visible_para("mantenimiento") is True
    assert op.es_visible_para("ingeniero") is False
    assert op.es_visible_para("admin") is False


# --- Tests de Caso de Uso ---


def test_use_case_operador_ve_solo_articulos_permitidos(articulos_muestra):
    repo = FakeSgeRepository(articulos_muestra)
    uc = ConsultarDocumentacionSgeUseCase(repo)
    resultado = uc.ejecutar(rol_usuario="operador")
    ids = [a.id for a in resultado]
    assert "sge-op-01" in ids
    assert "sge-pol-01" in ids
    assert "sge-mto-01" not in ids


def test_use_case_mantenimiento_ve_articulos_mantenimiento_y_operacion(articulos_muestra):
    repo = FakeSgeRepository(articulos_muestra)
    uc = ConsultarDocumentacionSgeUseCase(repo)
    resultado = uc.ejecutar(rol_usuario="mantenimiento")
    ids = [a.id for a in resultado]
    assert "sge-op-01" in ids
    assert "sge-mto-01" in ids
    assert "sge-pol-01" in ids


def test_use_case_admin_sin_filtro_ve_todos_los_articulos(articulos_muestra):
    repo = FakeSgeRepository(articulos_muestra)
    uc = ConsultarDocumentacionSgeUseCase(repo)
    resultado = uc.ejecutar(rol_usuario="admin")
    assert len(resultado) == len(articulos_muestra)


def test_use_case_admin_previsualiza_rol_operador(articulos_muestra):
    repo = FakeSgeRepository(articulos_muestra)
    uc = ConsultarDocumentacionSgeUseCase(repo)
    resultado = uc.ejecutar(rol_usuario="admin", rol_filtro="operador")
    ids = [a.id for a in resultado]
    assert "sge-op-01" in ids
    assert "sge-pol-01" in ids
    assert "sge-mto-01" not in ids


def test_use_case_operador_no_puede_previsualizar_admin(articulos_muestra):
    repo = FakeSgeRepository(articulos_muestra)
    uc = ConsultarDocumentacionSgeUseCase(repo)
    with pytest.raises(RolNoAutorizadoParaPrevisualizacionError):
        uc.ejecutar(rol_usuario="operador", rol_filtro="admin")


def test_use_case_operador_previsualiza_su_propio_rol(articulos_muestra):
    repo = FakeSgeRepository(articulos_muestra)
    uc = ConsultarDocumentacionSgeUseCase(repo)
    resultado = uc.ejecutar(rol_usuario="operador", rol_filtro="operador")
    ids = [a.id for a in resultado]
    assert "sge-op-01" in ids


# --- Tests de API HTTP (FastAPI & Cookies) ---


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def _crear_token(rol: str, exp_minutos: int = 60) -> str:
    settings = get_settings()
    token_service = JwtTokenService(settings.API_SECRET_KEY)
    expira = datetime.now(timezone.utc) + timedelta(minutes=exp_minutos)
    return token_service.generar(
        usuario_id="usr-123",
        usuario="test_user",
        expira_en=expira,
        rol=rol,
    )


def test_endpoint_sge_sin_autenticacion_devuelve_401(client):
    res = client.get("/api/v1/sge/documentacion")
    assert res.status_code == 401
    assert res.json()["detail"] == "credenciales_invalidas"


def test_endpoint_sge_con_cookie_httponly_operador(client):
    token = _crear_token(rol="operador")
    client.cookies.set("datamaq_token", token)

    res = client.get("/api/v1/sge/documentacion")
    assert res.status_code == 200
    articulos = res.json()
    assert isinstance(articulos, list)
    assert len(articulos) >= 1

    for art in articulos:
        assert "operador" in art["rolesPermitidos"]

    art_op = next(a for a in articulos if a["id"] == "sge-op-01")
    assert art_op["titulo"] == "Procedimiento Operativo: Paradas Operativas y Horario Pico"
    assert art_op["categoria"] == "operacion"
    assert "operador" in art_op["rolesPermitidos"]
    assert "mantenimiento" in art_op["rolesPermitidos"]
    assert "Escalonamiento de arranque de grandes motores" in art_op["puntosClave"]
    assert "No encender dos compresores simultáneos en horario pico (18 a 23 hs)" in art_op["accionesInmediatas"]
    assert art_op["referenciaIso"] == "Cláusula 8.1 - Planificación y Control Operativo"
    assert art_op["documentoUrl"] == "/archivos/sge/IT-EN-03.pdf"


def test_endpoint_sge_con_cookie_httponly_mantenimiento(client):
    token = _crear_token(rol="mantenimiento")
    client.cookies.set("datamaq_token", token)

    res = client.get("/api/v1/sge/documentacion")
    assert res.status_code == 200
    articulos = res.json()
    ids = [a["id"] for a in articulos]
    assert "sge-op-01" in ids
    assert "sge-mto-01" in ids


def test_endpoint_sge_con_cookie_httponly_ingeniero(client):
    token = _crear_token(rol="ingeniero")
    client.cookies.set("datamaq_token", token)

    res = client.get("/api/v1/sge/documentacion")
    assert res.status_code == 200
    articulos = res.json()
    ids = [a["id"] for a in articulos]
    assert "sge-mto-01" in ids
    assert "sge-enre-01" in ids
    assert "sge-enpi-01" in ids
    assert "sge-op-01" not in ids


def test_endpoint_sge_con_cookie_httponly_admin(client):
    token = _crear_token(rol="admin")
    client.cookies.set("datamaq_token", token)

    res = client.get("/api/v1/sge/documentacion")
    assert res.status_code == 200
    articulos = res.json()
    ids = [a["id"] for a in articulos]
    assert "sge-op-01" in ids
    assert "sge-mto-01" in ids
    assert "sge-enre-01" in ids
    assert "sge-enpi-01" in ids


def test_endpoint_sge_admin_previsualiza_rol_operador(client):
    token = _crear_token(rol="admin")
    client.cookies.set("datamaq_token", token)

    res = client.get("/api/v1/sge/documentacion?rol=operador")
    assert res.status_code == 200
    articulos = res.json()
    ids = [a["id"] for a in articulos]
    assert "sge-op-01" in ids
    assert "sge-mto-01" not in ids


def test_endpoint_sge_operador_intenta_previsualizar_admin_da_403(client):
    token = _crear_token(rol="operador")
    client.cookies.set("datamaq_token", token)

    res = client.get("/api/v1/sge/documentacion?rol=admin")
    assert res.status_code == 403
    assert "no tiene privilegios para previsualizar" in res.json()["detail"]


def test_endpoint_sge_con_header_authorization_bearer(client):
    token = _crear_token(rol="operador")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/v1/sge/documentacion", headers=headers)
    assert res.status_code == 200
    ids = [a["id"] for a in res.json()]
    assert "sge-op-01" in ids

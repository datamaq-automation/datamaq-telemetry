"""tests/unit/test_sge_competencias.py — Tests para registro de competencias ISO 50001 §7.2."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.use_cases.consultar_competencias_usuario import (
    ConsultarCompetenciasUsuarioUseCase,
)
from src.application.use_cases.registrar_acuse_capacitacion import (
    RegistrarAcuseCapacitacionUseCase,
)
from src.domain.sge.entities import ArticuloSge, RegistroCapacitacionSge
from src.domain.sge.exceptions import (
    ArticuloSgeNoEncontradoError,
    CapacitacionNoAutorizadaParaRolError,
    CapacitacionYaRegistradaError,
)
from src.domain.sge.ports import (
    RepositorioDocumentacionSgePort,
    RepositorioRegistroCapacitacionesSgePort,
)
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi.dependencies import get_usuarios_repository
from src.infrastructure.fastapi.routes.sge_router import (
    get_consultar_competencias_use_case,
    get_registrar_acuse_use_case,
)
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import get_settings


class FakeDocumentacionRepo(RepositorioDocumentacionSgePort):
    def __init__(self, articulos: list[ArticuloSge]):
        self._articulos = {a.id: a for a in articulos}

    def listar_todos(self) -> list[ArticuloSge]:
        return list(self._articulos.values())

    def listar_por_rol(self, rol: str) -> list[ArticuloSge]:
        return [a for a in self._articulos.values() if a.es_visible_para(rol)]

    def obtener_por_id(self, articulo_id: str) -> ArticuloSge | None:
        return self._articulos.get(articulo_id)


class FakeRegistroCapacitacionesRepo(RepositorioRegistroCapacitacionesSgePort):
    def __init__(self):
        self._registros: list[RegistroCapacitacionSge] = []

    def registrar(self, registro: RegistroCapacitacionSge) -> None:
        self._registros.append(registro)

    def listar_por_usuario(self, usuario_id: str) -> list[RegistroCapacitacionSge]:
        return [r for r in self._registros if r.usuario_id == usuario_id]

    def obtener_por_usuario_y_articulo(self, usuario_id: str, articulo_id: str) -> RegistroCapacitacionSge | None:
        return next(
            (r for r in self._registros if r.usuario_id == usuario_id and r.articulo_id == articulo_id),
            None,
        )

    def listar_todos(self) -> list[RegistroCapacitacionSge]:
        return list(self._registros)


@pytest.fixture
def repo_documentacion() -> FakeDocumentacionRepo:
    articulos = [
        ArticuloSge(
            id="it-en-03",
            titulo="Apagado y Modo Espera de Motores en TGBT",
            categoria="operacion",
            roles_permitidos=("operador", "mantenimiento", "ingeniero", "admin"),
            resumen="Procedimiento para desconexión en pausas operativas.",
            puntos_clave=("No dejar motores en vacío",),
            acciones_inmediatas=("Desactivar seccionador aguas abajo",),
            referencia_iso="ISO 50001:2018 §8.1",
        ),
        ArticuloSge(
            id="pol-sge-01",
            titulo="Política Energética Corporativa",
            categoria="politica",
            roles_permitidos=("operador", "mantenimiento", "ingeniero", "admin"),
            resumen="Compromiso de mejora continua del desempeño energético.",
            puntos_clave=("Reducción del SEC",),
            acciones_inmediatas=("Informar anomalías",),
            referencia_iso="ISO 50001:2018 §5.2",
        ),
        ArticuloSge(
            id="it-mto-04",
            titulo="Mantenimiento Predictivo Motores IE3/IE4",
            categoria="mantenimiento",
            roles_permitidos=("mantenimiento", "ingeniero", "admin"),
            resumen="Protocolo de inspección de rodamientos y cos phi.",
            puntos_clave=("Medición termográfica",),
            acciones_inmediatas=("Calibrar banco de capacitores",),
            referencia_iso="ISO 50001:2018 §6.3, §8.1",
        ),
    ]
    return FakeDocumentacionRepo(articulos)


@pytest.fixture
def repo_capacitaciones() -> FakeRegistroCapacitacionesRepo:
    return FakeRegistroCapacitacionesRepo()


def test_entidad_registro_capacitacion_inmutable():
    ahora = datetime.now(timezone.utc)
    registro = RegistroCapacitacionSge(
        id="reg-01",
        usuario_id="usr-123",
        articulo_id="it-en-03",
        rol_usuario="operador",
        fecha_completado=ahora,
        version_doc="1.0",
        comentarios="Leído y comprendido en puesto de trabajo",
    )
    assert registro.usuario_id == "usr-123"
    assert registro.articulo_id == "it-en-03"
    with pytest.raises(AttributeError):
        registro.usuario_id = "otro"  # type: ignore


def test_use_case_registrar_acuse_exitoso(repo_documentacion, repo_capacitaciones):
    uc = RegistrarAcuseCapacitacionUseCase(repo_documentacion, repo_capacitaciones)
    resultado = uc.ejecutar(
        usuario_id="usr-123",
        articulo_id="it-en-03",
        rol_usuario="operador",
        version_doc="1.0",
        comentarios="Entendido",
    )
    assert resultado.id is not None
    assert resultado.usuario_id == "usr-123"
    assert resultado.articulo_id == "it-en-03"

    # Verificar persistencia en repo
    guardados = repo_capacitaciones.listar_por_usuario("usr-123")
    assert len(guardados) == 1
    assert guardados[0].articulo_id == "it-en-03"


def test_use_case_registrar_acuse_articulo_no_existente_lanza_error(repo_documentacion, repo_capacitaciones):
    uc = RegistrarAcuseCapacitacionUseCase(repo_documentacion, repo_capacitaciones)
    with pytest.raises(ArticuloSgeNoEncontradoError):
        uc.ejecutar(
            usuario_id="usr-123",
            articulo_id="inexistente",
            rol_usuario="operador",
            version_doc="1.0",
        )


def test_use_case_registrar_acuse_rol_no_autorizado_lanza_error(repo_documentacion, repo_capacitaciones):
    uc = RegistrarAcuseCapacitacionUseCase(repo_documentacion, repo_capacitaciones)
    # it-mto-04 solo es para mantenimiento/ingeniero/admin, no para operador
    with pytest.raises(CapacitacionNoAutorizadaParaRolError):
        uc.ejecutar(
            usuario_id="usr-123",
            articulo_id="it-mto-04",
            rol_usuario="operador",
            version_doc="1.0",
        )


def test_use_case_registrar_acuse_duplicado_lanza_error(repo_documentacion, repo_capacitaciones):
    uc = RegistrarAcuseCapacitacionUseCase(repo_documentacion, repo_capacitaciones)
    uc.ejecutar(
        usuario_id="usr-123",
        articulo_id="it-en-03",
        rol_usuario="operador",
        version_doc="1.0",
    )
    with pytest.raises(CapacitacionYaRegistradaError):
        uc.ejecutar(
            usuario_id="usr-123",
            articulo_id="it-en-03",
            rol_usuario="operador",
            version_doc="1.0",
        )


def test_use_case_consultar_competencias_calcula_completadas_y_pendientes(repo_documentacion, repo_capacitaciones):
    uc_reg = RegistrarAcuseCapacitacionUseCase(repo_documentacion, repo_capacitaciones)
    uc_reg.ejecutar(
        usuario_id="usr-operador-1",
        articulo_id="it-en-03",
        rol_usuario="operador",
        version_doc="1.0",
    )

    uc_cons = ConsultarCompetenciasUsuarioUseCase(repo_documentacion, repo_capacitaciones)
    estado = uc_cons.ejecutar(usuario_id="usr-operador-1", rol_usuario="operador")

    # Para operador, los artículos visibles obligatorios son it-en-03 y pol-sge-01
    assert len(estado.capacitaciones_completadas) == 1
    assert estado.capacitaciones_completadas[0].articulo_id == "it-en-03"
    assert len(estado.capacitaciones_pendientes) == 1
    assert estado.capacitaciones_pendientes[0].id == "pol-sge-01"
    assert estado.porcentaje_cumplimiento == 50.0


# --- HTTP Endpoints Tests ---


@pytest.fixture
def client_competencias(repo_documentacion, repo_capacitaciones):
    app = create_app()
    mock_repo_usuarios = MagicMock()
    mock_repo_usuarios.obtener_por_id.return_value = None
    app.dependency_overrides[get_usuarios_repository] = lambda: mock_repo_usuarios

    uc_reg = RegistrarAcuseCapacitacionUseCase(repo_documentacion, repo_capacitaciones)
    uc_cons = ConsultarCompetenciasUsuarioUseCase(repo_documentacion, repo_capacitaciones)
    app.dependency_overrides[get_registrar_acuse_use_case] = lambda: uc_reg
    app.dependency_overrides[get_consultar_competencias_use_case] = lambda: uc_cons

    return TestClient(app)


def _crear_token(rol: str, exp_minutos: int = 60) -> str:
    settings = get_settings()
    token_service = JwtTokenService(settings.API_SECRET_KEY)
    expira = datetime.now(timezone.utc) + timedelta(minutes=exp_minutos)
    return token_service.generar(
        usuario_id="usr-123",
        usuario="test_operador",
        expira_en=expira,
        rol=rol,
    )


def test_endpoint_acuse_sin_auth_da_401(client_competencias):
    res = client_competencias.post(
        "/api/v1/sge/competencias/acuse",
        json={"articulo_id": "it-en-03", "version_doc": "1.0"},
    )
    assert res.status_code == 401


def test_endpoint_acuse_exitoso_y_consulta(client_competencias):
    token = _crear_token(rol="operador")
    client_competencias.cookies.set("datamaq_token", token)

    # 1. Registrar acuse
    res = client_competencias.post(
        "/api/v1/sge/competencias/acuse",
        json={
            "articulo_id": "it-en-03",
            "version_doc": "1.0",
            "comentarios": "Firmado digitalmente",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["articuloId"] == "it-en-03"
    assert data["usuarioId"] == "usr-123"

    # 2. Consultar mis competencias
    res_cons = client_competencias.get("/api/v1/sge/competencias/mis-capacitaciones")
    assert res_cons.status_code == 200
    res_data = res_cons.json()
    assert res_data["porcentajeCumplimiento"] == 50.0
    assert len(res_data["capacitacionesCompletadas"]) == 1
    assert len(res_data["capacitacionesPendientes"]) == 1

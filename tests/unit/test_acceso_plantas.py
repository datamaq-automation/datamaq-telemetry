"""tests/unit/test_acceso_plantas.py — R-02: asignación de plantas por usuario y permiso de cambio."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.dtos.auth_dto import AsignarPlantaRequestDTO, AsignarPlantasRequestDTO, PlantaAccesoDTO
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.domain.auth.entities import AccesoPlantaUsuario, UsuarioAuth
from src.domain.auth.exceptions import UsuarioNoEncontradoError
from src.domain.auth.ports import RepositorioAccesosPlantaPort, RepositorioUsuariosPort
from src.domain.auth.services import HashContrasenaService, PoliticaAccesoPlantasService
from src.domain.telemetria.entities import Planta
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import get_usuario_actual, get_usuarios_repository
from src.infrastructure.fastapi.server import create_app

T0 = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)

GARIN = Planta(id="planta-garin", organizacion_id="org-a", nombre="Garín")
PILAR = Planta(id="planta-pilar", organizacion_id="org-a", nombre="Pilar")
AJENA = Planta(id="planta-ajena", organizacion_id="org-b", nombre="Ajena")
PLANTAS = [GARIN, PILAR, AJENA]


class RepoAccesosEnMemoria(RepositorioAccesosPlantaPort):
    def __init__(self, accesos: list[AccesoPlantaUsuario] | None = None):
        self.accesos = list(accesos or [])

    def listar_por_usuario(self, usuario_id: str) -> list[AccesoPlantaUsuario]:
        return [a for a in self.accesos if a.usuario_id == usuario_id]

    def reemplazar(self, usuario_id: str, accesos: list[AccesoPlantaUsuario]) -> list[AccesoPlantaUsuario]:
        self.accesos = [a for a in self.accesos if a.usuario_id != usuario_id] + list(accesos)
        return self.listar_por_usuario(usuario_id)


class RepoUsuariosEnMemoria(RepositorioUsuariosPort):
    def __init__(self, usuarios: list[UsuarioAuth]):
        self.usuarios = {u.id: u for u in usuarios}

    def obtener_por_usuario(self, usuario: str) -> UsuarioAuth | None:
        return next((u for u in self.usuarios.values() if u.usuario == usuario), None)

    def obtener_por_id(self, usuario_id: str) -> UsuarioAuth | None:
        return self.usuarios.get(usuario_id)

    def guardar(self, usuario: UsuarioAuth) -> UsuarioAuth:
        self.usuarios[usuario.id] = usuario
        return usuario


def _usuario(id_: str = "u-1", rol: str = "operador", org: str | None = "org-a") -> UsuarioAuth:
    return UsuarioAuth(id=id_, usuario=f"{id_}@datamaq", hash_contrasena="x", rol=rol, organizacion_id=org)


def _repo_org() -> MagicMock:
    repo = MagicMock()
    repo.listar_plantas.side_effect = lambda org=None: [p for p in PLANTAS if org is None or p.organizacion_id == org]
    repo.obtener_planta_por_id.side_effect = lambda pid: next((p for p in PLANTAS if p.id == pid), None)
    return repo


# --- 1. Política de dominio ---


def test_politica_superadmin_ve_todas_las_plantas_y_puede_cambiar():
    resultado = PoliticaAccesoPlantasService.resolver("superadmin", None, PLANTAS, [])
    assert [p.id for p, _ in resultado] == ["planta-garin", "planta-pilar", "planta-ajena"]
    assert all(puede for _, puede in resultado)


def test_politica_sin_filas_devuelve_toda_la_organizacion_con_cambio():
    resultado = PoliticaAccesoPlantasService.resolver("operador", "org-a", PLANTAS, [])
    assert [(p.id, puede) for p, puede in resultado] == [("planta-garin", True), ("planta-pilar", True)]


def test_politica_sin_organizacion_ni_rol_global_no_ve_nada():
    assert PoliticaAccesoPlantasService.resolver("operador", None, PLANTAS, []) == []


def test_politica_con_filas_respeta_orden_de_asignacion_y_puede_cambiar():
    accesos = [
        AccesoPlantaUsuario("u-1", "planta-pilar", puede_cambiar=False, creado_en=T0),
        AccesoPlantaUsuario("u-1", "planta-garin", puede_cambiar=True, creado_en=T0 + timedelta(seconds=1)),
    ]
    resultado = PoliticaAccesoPlantasService.resolver("operador", "org-a", PLANTAS, accesos)
    assert [(p.id, puede) for p, puede in resultado] == [("planta-pilar", False), ("planta-garin", True)]


def test_politica_ignora_filas_de_otra_organizacion_e_inexistentes():
    accesos = [
        AccesoPlantaUsuario("u-1", "planta-ajena", puede_cambiar=True),
        AccesoPlantaUsuario("u-1", "planta-borrada", puede_cambiar=True),
        AccesoPlantaUsuario("u-1", "planta-garin", puede_cambiar=False),
    ]
    resultado = PoliticaAccesoPlantasService.resolver("admin", "org-a", PLANTAS, accesos)
    assert [(p.id, puede) for p, puede in resultado] == [("planta-garin", False)]


def test_politica_con_filas_y_ninguna_planta_valida_devuelve_lista_vacia():
    """Issue #85: usuario con filas en user_facility_access pero ninguna planta válida
    (todas borradas, inexistentes o de otra organización) no debe hacer fail-open
    a todas las plantas de su organización: debe devolver lista vacía (fail-close).
    """
    accesos = [
        AccesoPlantaUsuario("u-1", "planta-ajena", puede_cambiar=True),
        AccesoPlantaUsuario("u-1", "planta-borrada", puede_cambiar=True),
        AccesoPlantaUsuario("u-1", "planta-inexistente", puede_cambiar=False),
    ]
    resultado = PoliticaAccesoPlantasService.resolver("operador", "org-a", PLANTAS, accesos)
    assert resultado == []


# --- 2. Caso de uso ---


def test_use_case_resolver_mapea_a_dto_y_planta_activa_es_la_primera():
    accesos = RepoAccesosEnMemoria([AccesoPlantaUsuario("u-1", "planta-pilar", puede_cambiar=False)])
    use_case = GestionarAccesoPlantasUseCase(accesos, _repo_org())
    plantas = use_case.resolver("u-1", "operador", "org-a")
    assert plantas == [PlantaAccesoDTO(id="planta-pilar", nombre="Pilar", organizacion_id="org-a", puede_cambiar=False)]
    assert GestionarAccesoPlantasUseCase.planta_activa(plantas) == "planta-pilar"
    assert GestionarAccesoPlantasUseCase.planta_activa([]) is None


def test_planta_permitida_propia_se_devuelve_y_la_ajena_o_inexistente_no():
    use_case = GestionarAccesoPlantasUseCase(RepoAccesosEnMemoria(), _repo_org())
    assert use_case.resolver_planta_permitida("u-1", "operador", "org-a", "planta-pilar") == "planta-pilar"
    for planta_id in ("planta-ajena", "planta-inexistente"):
        with pytest.raises(PlantaNoEncontradaError):
            use_case.resolver_planta_permitida("u-1", "operador", "org-a", planta_id)


def test_planta_permitida_con_asignaciones_rechaza_la_no_asignada_de_su_org():
    accesos = RepoAccesosEnMemoria([AccesoPlantaUsuario("u-1", "planta-pilar", puede_cambiar=False)])
    use_case = GestionarAccesoPlantasUseCase(accesos, _repo_org())
    with pytest.raises(PlantaNoEncontradaError):
        use_case.resolver_planta_permitida("u-1", "operador", "org-a", "planta-garin")
    # Sin id pedido: la activa es la asignada, igual que planta_activa_id de /auth/me.
    assert use_case.resolver_planta_permitida("u-1", "operador", "org-a", None) == "planta-pilar"


def test_planta_permitida_con_asignaciones_invalidas_falla_cerrado():
    """Issue #85: si las asignaciones apuntan a plantas inexistentes o ajenas, no hay
    planta activa (None) y pedir cualquier planta de la org lanza PlantaNoEncontradaError.
    """
    accesos = RepoAccesosEnMemoria([AccesoPlantaUsuario("u-1", "planta-ajena", puede_cambiar=True)])
    use_case = GestionarAccesoPlantasUseCase(accesos, _repo_org())
    assert use_case.resolver("u-1", "operador", "org-a") == []
    assert use_case.resolver_planta_permitida("u-1", "operador", "org-a", None) is None
    with pytest.raises(PlantaNoEncontradaError):
        use_case.resolver_planta_permitida("u-1", "operador", "org-a", "planta-garin")


@pytest.mark.parametrize("rol", ["superadmin"])
def test_planta_permitida_roles_globales_acceden_a_cualquier_planta(rol):
    use_case = GestionarAccesoPlantasUseCase(RepoAccesosEnMemoria(), _repo_org())
    assert use_case.resolver_planta_permitida("u-1", rol, "org-a", "planta-ajena") == "planta-ajena"


def test_planta_permitida_sin_organizacion_no_tiene_planta_activa():
    use_case = GestionarAccesoPlantasUseCase(RepoAccesosEnMemoria(), _repo_org())
    assert use_case.resolver_planta_permitida("u-1", "operador", None, None) is None


def test_use_case_asignar_reemplaza_el_conjunto_y_deduplica():
    accesos = RepoAccesosEnMemoria([AccesoPlantaUsuario("u-1", "planta-garin", puede_cambiar=True)])
    use_case = GestionarAccesoPlantasUseCase(accesos, _repo_org(), RepoUsuariosEnMemoria([_usuario()]))
    dto = AsignarPlantasRequestDTO(
        plantas=[
            AsignarPlantaRequestDTO(planta_id="planta-pilar", puede_cambiar=False),
            AsignarPlantaRequestDTO(planta_id="planta-pilar", puede_cambiar=True),
        ]
    )
    resultado = use_case.asignar("u-1", dto)
    assert [(p.id, p.puede_cambiar) for p in resultado] == [("planta-pilar", False)]
    assert [a.planta_id for a in accesos.listar_por_usuario("u-1")] == ["planta-pilar"]


def test_use_case_asignar_lista_vacia_restaura_acceso_por_defecto():
    accesos = RepoAccesosEnMemoria([AccesoPlantaUsuario("u-1", "planta-pilar", puede_cambiar=False)])
    use_case = GestionarAccesoPlantasUseCase(accesos, _repo_org(), RepoUsuariosEnMemoria([_usuario()]))
    resultado = use_case.asignar("u-1", AsignarPlantasRequestDTO())
    assert [p.id for p in resultado] == ["planta-garin", "planta-pilar"]
    assert accesos.listar_por_usuario("u-1") == []


def test_use_case_asignar_rechaza_planta_de_otra_organizacion_sin_escribir():
    accesos = RepoAccesosEnMemoria([AccesoPlantaUsuario("u-1", "planta-garin", puede_cambiar=True)])
    use_case = GestionarAccesoPlantasUseCase(accesos, _repo_org(), RepoUsuariosEnMemoria([_usuario()]))
    dto = AsignarPlantasRequestDTO(plantas=[AsignarPlantaRequestDTO(planta_id="planta-ajena")])
    with pytest.raises(PlantaNoEncontradaError):
        use_case.asignar("u-1", dto)
    assert [a.planta_id for a in accesos.listar_por_usuario("u-1")] == ["planta-garin"]


def test_use_case_usuario_inexistente():
    use_case = GestionarAccesoPlantasUseCase(RepoAccesosEnMemoria(), _repo_org(), RepoUsuariosEnMemoria([]))
    with pytest.raises(UsuarioNoEncontradoError):
        use_case.listar_asignadas("nadie")


# --- 3. GET /auth/me expone plantas ---


def test_me_incluye_plantas_y_planta_activa():
    usuario = _usuario()
    accesos = RepoAccesosEnMemoria([AccesoPlantaUsuario("u-1", "planta-pilar", puede_cambiar=False)])
    acceso_plantas = GestionarAccesoPlantasUseCase(accesos, _repo_org())
    auth = AutenticarUsuarioUseCase(
        RepoUsuariosEnMemoria([usuario]), HashContrasenaService(), MagicMock(), 480, acceso_plantas=acceso_plantas
    )
    dto = auth.me({"sub": "u-1", "usuario": usuario.usuario, "rol": "operador", "org": "org-a"})
    assert dto.planta_activa_id == "planta-pilar"
    assert [(p.id, p.puede_cambiar) for p in dto.plantas] == [("planta-pilar", False)]


def test_me_con_asignaciones_invalidas_devuelve_plantas_vacias_y_sin_planta_activa():
    """Issue #85: usuario con filas en user_facility_access a plantas inexistentes o ajenas
    ve plantas=[] y planta_activa_id=None en /auth/me.
    """
    usuario = _usuario()
    accesos = RepoAccesosEnMemoria([AccesoPlantaUsuario("u-1", "planta-ajena", puede_cambiar=False)])
    acceso_plantas = GestionarAccesoPlantasUseCase(accesos, _repo_org())
    auth = AutenticarUsuarioUseCase(
        RepoUsuariosEnMemoria([usuario]), HashContrasenaService(), MagicMock(), 480, acceso_plantas=acceso_plantas
    )
    dto = auth.me({"sub": "u-1", "usuario": usuario.usuario, "rol": "operador", "org": "org-a"})
    assert dto.plantas == []
    assert dto.planta_activa_id is None


def test_me_sin_colaborador_de_plantas_mantiene_contrato_anterior():
    auth = AutenticarUsuarioUseCase(RepoUsuariosEnMemoria([]), HashContrasenaService(), MagicMock(), 480)
    dto = auth.me({"usuario": "u1", "rol": "admin"})
    assert dto.plantas == []
    assert dto.planta_activa_id is None


# --- 4. Router de administración ---


def _cliente(rol: str, org: str, usuarios: list[UsuarioAuth]) -> tuple[TestClient, RepoAccesosEnMemoria]:
    app = create_app()
    accesos = RepoAccesosEnMemoria()
    repo_usuarios = RepoUsuariosEnMemoria(usuarios)
    use_case = GestionarAccesoPlantasUseCase(accesos, _repo_org(), repo_usuarios)
    app.dependency_overrides[get_acceso_plantas_use_case] = lambda: use_case
    app.dependency_overrides[get_usuarios_repository] = lambda: repo_usuarios
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "admin-1", "rol": rol, "org": org}
    return TestClient(app), accesos


def test_router_put_y_get_plantas_usuario():
    client, accesos = _cliente("admin", "org-a", [_usuario()])
    body = {"plantas": [{"planta_id": "planta-garin", "puede_cambiar": False}]}
    resp = client.put("/api/v1/usuarios/u-1/plantas", json=body)
    assert resp.status_code == 200
    assert resp.json() == [
        {"id": "planta-garin", "nombre": "Garín", "organizacion_id": "org-a", "puede_cambiar": False}
    ]
    assert [a.planta_id for a in accesos.listar_por_usuario("u-1")] == ["planta-garin"]
    assert client.get("/api/v1/usuarios/u-1/plantas").json()[0]["id"] == "planta-garin"


def test_router_admin_no_administra_usuarios_de_otra_organizacion():
    client, _ = _cliente("admin", "org-b", [_usuario()])
    resp = client.put("/api/v1/usuarios/u-1/plantas", json={"plantas": []})
    assert resp.status_code == 403


def test_router_superadmin_administra_cualquier_organizacion():
    client, _ = _cliente("superadmin", "org-z", [_usuario()])
    resp = client.get("/api/v1/usuarios/u-1/plantas")
    assert resp.status_code == 200


def test_router_operador_recibe_403_y_planta_ajena_404():
    client, _ = _cliente("operador", "org-a", [_usuario()])
    assert client.get("/api/v1/usuarios/u-1/plantas").status_code == 403
    client, _ = _cliente("admin", "org-a", [_usuario()])
    resp = client.put("/api/v1/usuarios/u-1/plantas", json={"plantas": [{"planta_id": "planta-ajena"}]})
    assert resp.status_code == 404
    assert client.get("/api/v1/usuarios/inexistente/plantas").status_code == 404

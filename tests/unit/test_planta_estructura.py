import pytest
from fastapi.testclient import TestClient

from src.application.dtos.planta_estructura_dto import (
    CoordenadasZonaDTO,
    DispositivoLayoutDTO,
    GuardarLayoutRequestDTO,
    GuardarUnifilarRequestDTO,
    NodoUnifilarDTO,
    PosicionLayoutDTO,
    ZonaPlantaDTO,
)
from src.application.mappers.planta_estructura_mapper import PlantaEstructuraMapper
from src.application.use_cases.gestionar_planta_estructura import (
    GestionarPlantaEstructuraUseCase,
    PlantaNoEncontradaError,
)
from src.domain.telemetria.entities import (
    DispositivoLayout,
    NodoUnifilar,
    Organizacion,
    Planta,
    ZonaPlanta,
)
from src.domain.telemetria.exceptions import CoordenadaInvalidaError
from src.domain.telemetria.ports import RepositorioOrganizacionesPort
from src.domain.telemetria.value_objects import (
    CoordenadasZona,
    PosicionLayout,
    TipoNodoUnifilar,
)
from src.infrastructure.fastapi.dependencies import (
    get_planta_estructura_use_case,
    get_usuario_actual,
    requiere_rol_escritura,
)
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import Settings


class MockOrganizacionesRepo(RepositorioOrganizacionesPort):
    def __init__(self):
        self.organizaciones: dict[str, Organizacion] = {}
        self.plantas: dict[str, Planta] = {}
        self.nodos_unifilar: dict[str, list[NodoUnifilar]] = {}
        self.zonas: dict[str, list[ZonaPlanta]] = {}
        self.dispositivos_layout: dict[str, list[DispositivoLayout]] = {}

    def obtener_por_id(self, organizacion_id: str) -> Organizacion | None:
        return self.organizaciones.get(organizacion_id)

    def listar_organizaciones(self) -> list[Organizacion]:
        return list(self.organizaciones.values())

    def guardar_organizacion(self, org: Organizacion) -> Organizacion:
        self.organizaciones[org.id] = org
        return org

    def obtener_planta_por_id(self, planta_id: str) -> Planta | None:
        return self.plantas.get(planta_id)

    def listar_plantas(self, organizacion_id: str | None = None) -> list[Planta]:
        if organizacion_id:
            return [p for p in self.plantas.values() if p.organizacion_id == organizacion_id]
        return list(self.plantas.values())

    def guardar_planta(self, planta: Planta) -> Planta:
        self.plantas[planta.id] = planta
        return planta

    def obtener_nodos_unifilar(self, planta_id: str) -> list[NodoUnifilar]:
        return list(self.nodos_unifilar.get(planta_id, []))

    def guardar_nodos_unifilar(self, planta_id: str, nodos: list[NodoUnifilar]) -> list[NodoUnifilar]:
        self.nodos_unifilar[planta_id] = list(nodos)
        return list(nodos)

    def obtener_zonas_planta(self, planta_id: str) -> list[ZonaPlanta]:
        return list(self.zonas.get(planta_id, []))

    def obtener_dispositivos_layout(self, planta_id: str) -> list[DispositivoLayout]:
        return list(self.dispositivos_layout.get(planta_id, []))

    def guardar_layout_planta(
        self,
        planta_id: str,
        plano_svg_url: str | None,
        zonas: list[ZonaPlanta],
        dispositivos: list[DispositivoLayout],
    ) -> None:
        if planta_id in self.plantas:
            p = self.plantas[planta_id]
            self.plantas[planta_id] = Planta(
                id=p.id,
                organizacion_id=p.organizacion_id,
                nombre=p.nombre,
                direccion=p.direccion,
                latitud=p.latitud,
                longitud=p.longitud,
                layout_svg_url=plano_svg_url,
                creado_en=p.creado_en,
                actualizado_en=p.actualizado_en,
            )
        self.zonas[planta_id] = list(zonas)
        self.dispositivos_layout[planta_id] = list(dispositivos)


# --- 1. Tests de Dominio y Value Objects ---


def test_coordenadas_zona_validas_y_fuera_de_rango():
    coords = CoordenadasZona(x_porcentaje=10.5, y_porcentaje=20.0, ancho_porcentaje=30.0, alto_porcentaje=40.0)
    assert coords.x_porcentaje == 10.5
    assert coords.ancho_porcentaje == 30.0

    with pytest.raises(CoordenadaInvalidaError):
        CoordenadasZona(x_porcentaje=-1.0, y_porcentaje=20.0, ancho_porcentaje=30.0, alto_porcentaje=40.0)

    with pytest.raises(CoordenadaInvalidaError):
        CoordenadasZona(x_porcentaje=10.0, y_porcentaje=105.0, ancho_porcentaje=30.0, alto_porcentaje=40.0)


def test_posicion_layout_valida_y_fuera_de_rango():
    pos = PosicionLayout(x_porcentaje=50.0, y_porcentaje=75.0)
    assert pos.x_porcentaje == 50.0

    with pytest.raises(CoordenadaInvalidaError):
        PosicionLayout(x_porcentaje=101.0, y_porcentaje=50.0)


def test_tipo_nodo_unifilar_enum():
    assert TipoNodoUnifilar.ACOMETIDA.value == "acometida"
    assert TipoNodoUnifilar.TRANSFORMADOR.value == "transformador"
    assert TipoNodoUnifilar.TGBT.value == "tgbt"
    assert TipoNodoUnifilar.SECCIONAL.value == "seccional"
    assert TipoNodoUnifilar.CARGA.value == "carga"


# --- 2. Tests de Mappers ---


def test_mapper_nodo_unifilar():
    nodo = NodoUnifilar(
        id="node-1",
        planta_id="plant-1",
        parent_id=None,
        nombre="Acometida MT",
        tipo=TipoNodoUnifilar.ACOMETIDA,
        device_id="dev-1",
        tension_nominal_v=13200.0,
        capacidad_nominal_kva=1000.0,
        orden=0,
    )
    dto = PlantaEstructuraMapper.nodo_to_dto(nodo)
    assert dto.id == "node-1"
    assert dto.tipo == "acometida"
    assert dto.tension_nominal_V == 13200.0

    nodo_rebuilt = PlantaEstructuraMapper.dto_to_nodo(dto, "plant-1")
    assert nodo_rebuilt.id == "node-1"
    assert nodo_rebuilt.tipo == TipoNodoUnifilar.ACOMETIDA


def test_mapper_zona_y_dispositivo_layout():
    zona = ZonaPlanta(
        id="zone-1",
        planta_id="plant-1",
        nombre="Nave Inyección",
        coordenadas=CoordenadasZona(x_porcentaje=10.0, y_porcentaje=15.0, ancho_porcentaje=40.0, alto_porcentaje=30.0),
    )
    zdto = PlantaEstructuraMapper.zona_to_dto(zona)
    assert zdto.nombre == "Nave Inyección"
    assert zdto.coordenadas.ancho_porcentaje == 40.0

    disp = DispositivoLayout(
        id="dl-1",
        planta_id="plant-1",
        device_id="dev-10",
        zona_id="zone-1",
        posicion=PosicionLayout(x_porcentaje=25.0, y_porcentaje=30.0),
    )
    ddto = PlantaEstructuraMapper.disp_layout_to_dto(disp)
    assert ddto.device_id == "dev-10"
    assert ddto.posicion.x_porcentaje == 25.0


# --- 3. Tests de Casos de Uso ---


def test_gestionar_unifilar_use_case():
    repo = MockOrganizacionesRepo()
    planta = Planta(id="plant-1", organizacion_id="org-1", nombre="Planta Garín")
    repo.guardar_planta(planta)

    use_case = GestionarPlantaEstructuraUseCase(repo)

    # 1. Obtener inicial (vacío)
    res_inicial = use_case.obtener_unifilar("plant-1")
    assert res_inicial.planta_id == "plant-1"
    assert res_inicial.nombre_planta == "Planta Garín"
    assert len(res_inicial.nodos) == 0

    # 2. Guardar estructura unifilar en árbol
    req = GuardarUnifilarRequestDTO(
        nodos=[
            NodoUnifilarDTO(
                id="n1",
                parent_id=None,
                nombre="Acometida MT",
                tipo="acometida",
                device_id="dev-1",
                tension_nominal_V=13200.0,
                capacidad_nominal_kVA=1000.0,
                orden=0,
            ),
            NodoUnifilarDTO(
                id="n2",
                parent_id="n1",
                nombre="Transformador Trafo-1",
                tipo="transformador",
                device_id="dev-2",
                tension_nominal_V=380.0,
                capacidad_nominal_kVA=800.0,
                orden=1,
            ),
            NodoUnifilarDTO(
                id="n3",
                parent_id="n2",
                nombre="TGBT Principal",
                tipo="tgbt",
                device_id="dev-3",
                tension_nominal_V=380.0,
                capacidad_nominal_kVA=800.0,
                orden=2,
            ),
        ]
    )
    res_guardado = use_case.guardar_unifilar("plant-1", req)
    assert len(res_guardado.nodos) == 3
    assert res_guardado.nodos[1].parent_id == "n1"

    # 3. Consulta sin especificar planta_id (resuelve planta por defecto)
    res_default = use_case.obtener_unifilar()
    assert res_default.planta_id == "plant-1"
    assert len(res_default.nodos) == 3


def test_gestionar_layout_use_case():
    repo = MockOrganizacionesRepo()
    planta = Planta(id="plant-1", organizacion_id="org-1", nombre="Planta Pilar")
    repo.guardar_planta(planta)

    use_case = GestionarPlantaEstructuraUseCase(repo)

    # Guardar layout
    req = GuardarLayoutRequestDTO(
        plano_svg_url="https://cdn.datamaq.com.ar/planos/pilar.svg",
        zonas=[
            ZonaPlantaDTO(
                id="z1",
                nombre="Nave A",
                coordenadas=CoordenadasZonaDTO(
                    x_porcentaje=0.0, y_porcentaje=0.0, ancho_porcentaje=50.0, alto_porcentaje=50.0
                ),
            )
        ],
        dispositivos=[
            DispositivoLayoutDTO(
                device_id="dev-pilar-1",
                zona_id="z1",
                posicion=PosicionLayoutDTO(x_porcentaje=20.0, y_porcentaje=20.0),
            )
        ],
    )
    layout = use_case.guardar_layout("plant-1", req)
    assert layout.plano_svg_url == "https://cdn.datamaq.com.ar/planos/pilar.svg"
    assert len(layout.zonas) == 1
    assert len(layout.dispositivos) == 1
    assert layout.dispositivos[0].device_id == "dev-pilar-1"

    # Obtener layout
    obtenido = use_case.obtener_layout("plant-1")
    assert obtenido.plano_svg_url == "https://cdn.datamaq.com.ar/planos/pilar.svg"
    assert len(obtenido.zonas) == 1


def test_planta_no_encontrada_error():
    repo = MockOrganizacionesRepo()
    use_case = GestionarPlantaEstructuraUseCase(repo)

    with pytest.raises(PlantaNoEncontradaError):
        use_case.obtener_unifilar("planta-inexistente")

    with pytest.raises(PlantaNoEncontradaError):
        use_case.obtener_layout()


# --- 4. Tests de Rutas FastAPI ---


@pytest.fixture
def api_test_client():
    repo = MockOrganizacionesRepo()
    planta = Planta(id="plant-test", organizacion_id="org-test", nombre="Planta Test")
    repo.guardar_planta(planta)

    use_case = GestionarPlantaEstructuraUseCase(repo)

    settings = Settings(
        API_SECRET_KEY="test-secret-key-very-secure-for-testing",
        AUTH_REQUIRED=False,
        DEBUG=True,
    )
    app = create_app(settings)
    app.dependency_overrides[get_planta_estructura_use_case] = lambda: use_case
    app.dependency_overrides[get_usuario_actual] = lambda: {"username": "admin", "rol": "administrador"}
    app.dependency_overrides[requiere_rol_escritura] = lambda: {"username": "admin", "rol": "administrador"}

    return TestClient(app), use_case


def test_routes_unifilar_y_layout(api_test_client):
    client, _ = api_test_client

    # 1. GET /api/v1/planta/unifilar
    res = client.get("/api/v1/planta/unifilar")
    assert res.status_code == 200
    data = res.json()
    assert data["planta_id"] == "plant-test"
    assert data["nodos"] == []

    # 2. PUT /api/v1/plantas/plant-test/unifilar
    payload_unifilar = {
        "nodos": [
            {
                "id": "node-1",
                "parent_id": None,
                "nombre": "Acometida General",
                "tipo": "acometida",
                "device_id": "D48C49F03564",
                "tension_nominal_V": 380.0,
                "capacidad_nominal_kVA": 500.0,
                "orden": 0,
            }
        ]
    }
    res_put = client.put("/api/v1/plantas/plant-test/unifilar", json=payload_unifilar)
    assert res_put.status_code == 200
    assert len(res_put.json()["nodos"]) == 1

    # 3. GET /api/v1/plantas/plant-test/unifilar
    res_get = client.get("/api/v1/plantas/plant-test/unifilar")
    assert res_get.status_code == 200
    assert res_get.json()["nodos"][0]["nombre"] == "Acometida General"

    # 4. PUT /api/v1/plantas/plant-test/layout
    payload_layout = {
        "plano_svg_url": "https://cdn.datamaq.com.ar/svg/layout.svg",
        "zonas": [
            {
                "id": "z-1",
                "nombre": "Sala de Compresores",
                "coordenadas": {
                    "x_porcentaje": 10.0,
                    "y_porcentaje": 20.0,
                    "ancho_porcentaje": 30.0,
                    "alto_porcentaje": 25.0,
                },
            }
        ],
        "dispositivos": [
            {
                "device_id": "D48C49F03564",
                "zona_id": "z-1",
                "posicion": {
                    "x_porcentaje": 15.0,
                    "y_porcentaje": 22.0,
                },
            }
        ],
    }
    res_put_layout = client.put("/api/v1/plantas/plant-test/layout", json=payload_layout)
    assert res_put_layout.status_code == 200
    assert res_put_layout.json()["plano_svg_url"] == "https://cdn.datamaq.com.ar/svg/layout.svg"

    # 5. GET /api/v1/planta/layout
    res_get_layout = client.get("/api/v1/planta/layout")
    assert res_get_layout.status_code == 200
    assert len(res_get_layout.json()["zonas"]) == 1
    assert res_get_layout.json()["dispositivos"][0]["device_id"] == "D48C49F03564"

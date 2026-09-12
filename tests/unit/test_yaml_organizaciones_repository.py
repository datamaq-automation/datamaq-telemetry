from src.domain.telemetria.value_objects import ModoFreeTier, TipoNodoUnifilar
from src.infrastructure.yaml.repositories.organizaciones_repository import (
    YamlOrganizacionesRepository,
)


def test_yaml_organizaciones_repository(tmp_path):
    subfolder = tmp_path / "organizaciones"
    subfolder.mkdir()
    yaml_file = subfolder / "test_org.yml"
    yaml_file.write_text(
        """
organizaciones:
  - id: "org-test-1"
    nombre: "Test Org"
    plan_id: "plan-pro"
    cuit: "20-99999999-9"
    email_contacto: "test@org.com"
    telefono_contacto: "123456"
    modo_free: "COMUNIDAD_ABIERTA"
    plantas:
      - id: "planta-test-1"
        nombre: "Planta Test"
        direccion: "Calle Test 123"
        nodos_unifilar:
          - id: "nodo-t1"
            nombre: "Nodo Principal"
            tipo: "TGBT"
        zonas:
          - id: "zona-t1"
            nombre: "Zona A"
            color: "#00FF00"
            coordenadas:
              x: 5.0
              y: 5.0
              ancho: 50.0
              alto: 50.0
        dispositivos_layout:
          - dispositivo_id: "dev-t1"
            zona_id: "zona-t1"
            posicion:
              x: 10.0
              y: 10.0
""",
        encoding="utf-8",
    )

    repo = YamlOrganizacionesRepository(data_dir=str(tmp_path))

    # Test listar y obtener por ID
    orgs = repo.listar_organizaciones()
    assert len(orgs) == 1
    assert orgs[0].id == "org-test-1"
    assert orgs[0].nombre == "Test Org"
    assert orgs[0].modo_free == ModoFreeTier.PRIVADO_BASICO

    org = repo.obtener_por_id("org-test-1")
    assert org is not None
    assert org.nombre == "Test Org"

    assert repo.obtener_por_id("inexistente") is None

    # Test plantas
    plantas = repo.listar_plantas("org-test-1")
    assert len(plantas) == 1
    assert plantas[0].id == "planta-test-1"

    planta = repo.obtener_planta_por_id("planta-test-1")
    assert planta is not None
    assert planta.nombre == "Planta Test"

    # Test nodos unifilar
    nodos = repo.obtener_nodos_unifilar("planta-test-1")
    assert len(nodos) == 1
    assert nodos[0].id == "nodo-t1"
    assert nodos[0].tipo == TipoNodoUnifilar.TGBT

    # Test zonas
    zonas = repo.obtener_zonas_planta("planta-test-1")
    assert len(zonas) == 1
    assert zonas[0].id == "zona-t1"
    assert zonas[0].coordenadas.ancho_porcentaje == 50.0

    # Test layout dispositivos
    layout = repo.obtener_dispositivos_layout("planta-test-1")
    assert len(layout) == 1
    assert layout[0].device_id == "dev-t1"
    assert layout[0].posicion.x_porcentaje == 10.0


def test_yaml_organizaciones_repository_casos_borde(tmp_path):
    subfolder = tmp_path / "corrupted"
    subfolder.mkdir()

    # Archivo vacío
    file_empty = subfolder / "empty.yml"
    file_empty.write_text("", encoding="utf-8")

    # Archivo inválido
    file_invalid = subfolder / "invalid.yml"
    file_invalid.write_text("::: invalid yaml content :::", encoding="utf-8")

    # Archivo dict sin id
    file_no_id = subfolder / "no_id.yml"
    file_no_id.write_text("foo: bar", encoding="utf-8")

    repo = YamlOrganizacionesRepository(data_dir=str(tmp_path))
    assert repo.listar_organizaciones() == []
    assert repo.obtener_por_id("any") is None
    assert repo.listar_plantas() == []
    assert repo.obtener_planta_por_id("any") is None

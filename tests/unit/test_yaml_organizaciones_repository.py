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


def test_yaml_organizaciones_repository_estructura_modular_isa95(tmp_path):
    # Nivel 1 & 2: organizaciones/org-acme/
    org_dir = tmp_path / "organizaciones" / "org-acme"
    org_dir.mkdir(parents=True)
    org_file = org_dir / "organizacion.yml"
    org_file.write_text(
        """
id: "org-acme"
nombre: "Acme Industrial S.A."
plan_id: "plan-pro"
cuit: "30-11223344-5"
email_contacto: "contacto@acme.com"
telefono_contacto: "+541199998888"
modo_free: "PRIVADO_BASICO"
""",
        encoding="utf-8",
    )

    # Nivel 2 & 3: plantas/planta-pacheco/
    planta_dir = org_dir / "plantas" / "planta-pacheco"
    planta_dir.mkdir(parents=True)
    planta_file = planta_dir / "planta.yml"
    planta_file.write_text(
        """
id: "planta-pacheco"
nombre: "Planta Pacheco"
direccion: "Ruta 9 Km 35"
latitud: -34.45
longitud: -58.63
layout_svg_url: "/svg/pacheco.svg"
""",
        encoding="utf-8",
    )

    # Nivel 3: unifilar.yml
    unifilar_file = planta_dir / "unifilar.yml"
    unifilar_file.write_text(
        """
nodos:
  - id: "nodo-trafo"
    nombre: "Transformador 1"
    tipo: "TRANSFORMADOR"
    tension_nominal_v: 13200.0
    capacidad_nominal_kva: 1000.0
  - id: "nodo-horno"
    nombre: "Horno Inducción"
    tipo: "CARGA"
    padre_id: "nodo-trafo"
    dispositivo_id: "dev-horno-1"
    potencia_nominal_kw: 300.0
    uso_significativo: true
    categoria_uso: "PROCESO_PRODUCTIVO"
    variable_relevante: "toneladas_acero"
""",
        encoding="utf-8",
    )

    # Nivel 3: layout.yml
    layout_file = planta_dir / "layout.yml"
    layout_file.write_text(
        """
zonas:
  - id: "zona-forja"
    nombre: "Nave Forja"
    color: "#FF0000"
    coordenadas:
      x: 5.0
      y: 10.0
      ancho: 80.0
      alto: 40.0
dispositivos:
  - dispositivo_id: "dev-horno-1"
    zona_id: "zona-forja"
    posicion:
      x: 15.0
      y: 20.0
""",
        encoding="utf-8",
    )

    repo = YamlOrganizacionesRepository(data_dir=str(tmp_path))

    # Verificar organización
    orgs = repo.listar_organizaciones()
    assert len(orgs) == 1
    assert orgs[0].id == "org-acme"
    assert orgs[0].nombre == "Acme Industrial S.A."

    org = repo.obtener_por_id("org-acme")
    assert org is not None
    assert org.cuit == "30-11223344-5"

    # Verificar planta asociada
    plantas = repo.listar_plantas(organizacion_id="org-acme")
    assert len(plantas) == 1
    assert plantas[0].id == "planta-pacheco"
    assert plantas[0].nombre == "Planta Pacheco"
    assert plantas[0].organizacion_id == "org-acme"

    # Verificar unifilar
    nodos = repo.obtener_nodos_unifilar("planta-pacheco")
    assert len(nodos) == 2
    assert nodos[0].id == "nodo-trafo"
    assert nodos[0].tipo == TipoNodoUnifilar.TRANSFORMADOR
    assert nodos[1].id == "nodo-horno"
    assert nodos[1].uso_significativo is True
    assert nodos[1].potencia_nominal_kw == 300.0
    assert nodos[1].variable_relevante == "toneladas_acero"

    # Verificar zonas y layout
    zonas = repo.obtener_zonas_planta("planta-pacheco")
    assert len(zonas) == 1
    assert zonas[0].id == "zona-forja"

    disp_layout = repo.obtener_dispositivos_layout("planta-pacheco")
    assert len(disp_layout) == 1
    assert disp_layout[0].device_id == "dev-horno-1"
    assert disp_layout[0].posicion.x_porcentaje == 15.0

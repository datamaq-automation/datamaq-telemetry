"""tests/unit/test_slug_planta.py — slug legible de planta (decisión 2026-09-25)."""

from src.domain.telemetria.entities import Planta, generar_slug_planta
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository
from src.infrastructure.yaml.verificador_slugs_planta import verificar_slugs_planta


def test_generar_slug_planta_normaliza_espacios_y_mayusculas():
    assert generar_slug_planta("Planta Principal UPP") == "planta-principal-upp"


def test_generar_slug_planta_remueve_acentos_y_caracteres_no_alfanumericos():
    assert generar_slug_planta("Planta San Martín (Sur)") == "planta-san-martin-sur"


def test_generar_slug_planta_colapsa_guiones_repetidos():
    assert generar_slug_planta("  Planta   Norte  ") == "planta-norte"


def test_planta_deriva_slug_del_nombre_si_no_se_declara():
    planta = Planta(id="p1", organizacion_id="org-1", nombre="Cableco Buenos Aires")
    assert planta.slug == "cableco-buenos-aires"


def test_planta_respeta_slug_declarado_aunque_no_coincida_con_el_nombre():
    # Fijo al crearse (no mutable): si la planta se renombra, el slug declarado no cambia solo.
    planta = Planta(id="p1", organizacion_id="org-1", nombre="Planta Renombrada", slug="upp-gaarin")
    assert planta.slug == "upp-gaarin"


def _escribir_yaml(tmp_path, plantas_org_a: list[str], plantas_org_b: list[str] | None = None):
    subfolder = tmp_path / "organizaciones"
    subfolder.mkdir()
    yaml_file = subfolder / "test_org.yml"
    lineas = [
        "organizaciones:",
        '  - id: "org-a"',
        '    nombre: "Org A"',
        "    plantas:",
    ]
    for i, nombre in enumerate(plantas_org_a):
        lineas += [f'      - id: "planta-a-{i}"', f'        nombre: "{nombre}"']
    if plantas_org_b:
        lineas += ['  - id: "org-b"', '    nombre: "Org B"', "    plantas:"]
        for i, nombre in enumerate(plantas_org_b):
            lineas += [f'      - id: "planta-b-{i}"', f'        nombre: "{nombre}"']
    yaml_file.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def test_verificar_slugs_planta_sin_colisiones(tmp_path):
    _escribir_yaml(tmp_path, ["Planta Norte", "Planta Sur"])
    resultado = verificar_slugs_planta(YamlOrganizacionesRepository(data_dir=str(tmp_path)))
    assert resultado == {"plantas": 2, "colisiones": 0}


def test_verificar_slugs_planta_detecta_colision_en_la_misma_organizacion(tmp_path):
    _escribir_yaml(tmp_path, ["Planta Norte", "Planta  Norte"])
    resultado = verificar_slugs_planta(YamlOrganizacionesRepository(data_dir=str(tmp_path)))
    assert resultado == {"plantas": 2, "colisiones": 1}


def test_verificar_slugs_planta_no_reporta_colision_entre_organizaciones_distintas(tmp_path):
    _escribir_yaml(tmp_path, ["Planta Norte"], plantas_org_b=["Planta Norte"])
    resultado = verificar_slugs_planta(YamlOrganizacionesRepository(data_dir=str(tmp_path)))
    assert resultado == {"plantas": 2, "colisiones": 0}


def test_verificar_slugs_planta_con_yaml_real():
    resultado = verificar_slugs_planta(YamlOrganizacionesRepository(data_dir="data"))
    assert resultado["colisiones"] == 0

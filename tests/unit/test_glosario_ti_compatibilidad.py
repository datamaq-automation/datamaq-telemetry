"""tests/unit/test_glosario_ti_compatibilidad.py — Glosario TI, paso 1 (decisión 2026-10-13).

El YAML de datamaq-data usa los nombres viejos (`invertido`, `orden_fases`). El paso 1 agrega los nombres nuevos
(`polaridad_ti`, `asociacion_tension_corriente`) sin cambiar lo que devuelve el repositorio: un YAML con los nombres
viejos sigue dando la misma instalación, y si vienen los dos, gana el nuevo.
"""

from pathlib import Path

from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

ORGANIZACIONES = """organizaciones:
  - id: org-1
    nombre: Uno
    plantas:
      - id: p1
        nombre: Planta
        medidores:
          - {{id: m1, fases_con_ti: [R, S], correccion_angular_fases: "R:180,S:-120", {campos}}}
"""


def _instalacion(tmp_path: Path, nombre: str, campos: str):
    carpeta = tmp_path / nombre
    carpeta.mkdir()
    (carpeta / "organizaciones.yml").write_text(ORGANIZACIONES.format(campos=campos), encoding="utf-8")
    return YamlOrganizacionesRepository(str(carpeta)).obtener_instalacion_medidor("m1")


def test_yaml_con_nombres_viejos_da_la_instalacion_de_hoy(tmp_path: Path) -> None:
    inst = _instalacion(tmp_path, "viejo", "invertido: true, orden_fases: [S, R, T]")

    assert inst is not None
    assert inst.invertido is True
    assert inst.orden_fases == ["S", "R", "T"]
    assert inst.correccion_angular_fases == "R:180,S:-120"
    assert inst.fases_con_ti == ["R", "S"]


def test_yaml_con_nombres_nuevos_da_la_misma_instalacion_que_los_viejos(tmp_path: Path) -> None:
    viejo = _instalacion(tmp_path, "viejo", "invertido: true, orden_fases: [S, R, T]")
    nuevo = _instalacion(tmp_path, "nuevo", "polaridad_ti: true, asociacion_tension_corriente: [S, R, T]")

    assert nuevo == viejo


def test_si_vienen_los_dos_nombres_gana_el_nuevo(tmp_path: Path) -> None:
    inst = _instalacion(
        tmp_path,
        "ambos",
        "invertido: false, polaridad_ti: true, orden_fases: [R, S, T], asociacion_tension_corriente: [S, R, T]",
    )

    assert inst is not None
    assert inst.invertido is True
    assert inst.orden_fases == ["S", "R", "T"]

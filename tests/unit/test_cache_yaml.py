"""tests/unit/test_cache_yaml.py — Caché de los YAML de data/ invalidada por mtime (#14).

Cada request del unifilar parseaba data/ entero ~40 veces (~165 ms por parseo). La caché tiene que servir datos
nuevos apenas cambia un archivo, sin reiniciar el servicio: data/ se actualiza con `git pull` a mano en el VPS.
"""

import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from src.infrastructure.yaml import loaders
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

ORG_YML = """organizaciones:
  - id: org-1
    nombre: {nombre}
    plantas: []
"""


@pytest.fixture(autouse=True)
def _cache_limpia():
    loaders.limpiar_cache_yaml()
    yield
    loaders.limpiar_cache_yaml()


@pytest.fixture
def parseos():
    """Cuenta los parseos reales (no las llamadas, que pasan por la caché)."""
    contador = {"n": 0}
    original = loaders._parsear_organizaciones_completas

    def _contado(data_dir: str) -> list[dict]:
        contador["n"] += 1
        return original(data_dir)

    with patch.object(loaders, "_parsear_organizaciones_completas", _contado):
        yield contador


def _escribir(ruta: Path, contenido: str) -> None:
    """Escribe y adelanta el mtime 1 s: el cambio se ve aunque el filesystem tenga resolución gruesa."""
    ruta.write_text(contenido, encoding="utf-8")
    st = ruta.stat()
    os.utime(ruta, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))


def test_varias_lecturas_sin_cambios_parsean_una_vez(tmp_path, parseos):
    _escribir(tmp_path / "organizaciones.yml", ORG_YML.format(nombre="Uno"))
    repo = YamlOrganizacionesRepository(str(tmp_path))
    for _ in range(5):
        assert repo.obtener_por_id("org-1") is not None
    assert parseos["n"] == 1


def test_un_cambio_en_el_archivo_se_ve_sin_reiniciar(tmp_path, parseos):
    archivo = tmp_path / "organizaciones.yml"
    _escribir(archivo, ORG_YML.format(nombre="Uno"))
    repo = YamlOrganizacionesRepository(str(tmp_path))
    assert repo.obtener_por_id("org-1").nombre == "Uno"
    _escribir(archivo, ORG_YML.format(nombre="Dos"))
    assert repo.obtener_por_id("org-1").nombre == "Dos"
    assert parseos["n"] == 2


def test_un_archivo_nuevo_invalida_la_cache(tmp_path, parseos):
    _escribir(tmp_path / "organizaciones.yml", ORG_YML.format(nombre="Uno"))
    repo = YamlOrganizacionesRepository(str(tmp_path))
    assert repo.obtener_por_id("org-2") is None
    sub = tmp_path / "extra"
    sub.mkdir()
    _escribir(sub / "otra.yml", "organizaciones:\n  - id: org-2\n    nombre: Otra\n")
    assert repo.obtener_por_id("org-2") is not None


def test_instancias_distintas_comparten_la_cache(tmp_path, parseos):
    """Las dependencias crean un repositorio por request: la caché vive a nivel de módulo."""
    _escribir(tmp_path / "organizaciones.yml", ORG_YML.format(nombre="Uno"))
    for _ in range(3):
        YamlOrganizacionesRepository(str(tmp_path)).listar_organizaciones()
    assert parseos["n"] == 1


def test_hilos_concurrentes_con_cache_fria_parsean_una_vez(tmp_path, parseos):
    """Los endpoints son síncronos y corren en el threadpool."""
    _escribir(tmp_path / "organizaciones.yml", ORG_YML.format(nombre="Uno"))
    barrera = threading.Barrier(8)
    errores: list[BaseException] = []

    def _leer() -> None:
        try:
            barrera.wait()
            assert YamlOrganizacionesRepository(str(tmp_path)).obtener_por_id("org-1") is not None
        except BaseException as e:
            errores.append(e)

    hilos = [threading.Thread(target=_leer) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert errores == []
    assert parseos["n"] == 1


def test_facturas_tambien_se_invalidan_por_mtime(tmp_path):
    archivo = tmp_path / "facturas_distribuidora.yml"
    _escribir(archivo, "facturas:\n  - planta_id: p1\n")
    assert len(loaders.cargar_facturas_distribuidora(str(tmp_path))) == 1
    _escribir(archivo, "facturas:\n  - planta_id: p1\n  - planta_id: p2\n")
    assert len(loaders.cargar_facturas_distribuidora(str(tmp_path))) == 2


def test_mutar_el_resultado_no_corrompe_la_cache(tmp_path):
    """Si un consumidor muta lo que recibe (append, setdefault, pop, asignar, sort), la llamada siguiente, de este
    request o de otro hilo, tiene que ver los datos del archivo, no los mutados."""
    _escribir(
        tmp_path / "organizaciones.yml",
        """organizaciones:
  - id: org-1
    nombre: Uno
    plantas:
      - id: p1
        nombre: Planta
        medidores:
          - {id: m1, orden_fases: [R, S, T]}
""",
    )
    del_archivo = loaders._parsear_organizaciones_completas(str(tmp_path))  # Parseo fresco, fuera de la caché.
    mutado = loaders.cargar_organizaciones_completas(str(tmp_path))
    org = mutado[0]
    org["nombre"] = "Pisado"
    org.setdefault("extra", 1)
    org["plantas"].append({"id": "p2"})
    org["plantas"][0]["medidores"][0]["orden_fases"].sort(reverse=True)
    org["plantas"][0].pop("nombre")
    mutado.clear()

    assert loaders.cargar_organizaciones_completas(str(tmp_path)) == del_archivo


def test_una_lista_que_escapa_a_una_entidad_no_es_la_de_la_cache(tmp_path):
    _escribir(
        tmp_path / "organizaciones.yml",
        """organizaciones:
  - id: org-1
    nombre: Uno
    plantas:
      - id: p1
        nombre: Planta
        medidores:
          - {id: m1, orden_fases: [R, S, T]}
""",
    )
    repo = YamlOrganizacionesRepository(str(tmp_path))
    instalacion = repo.obtener_instalacion_medidor("m1")
    assert instalacion is not None and instalacion.orden_fases is not None
    instalacion.orden_fases.reverse()
    otra = repo.obtener_instalacion_medidor("m1")
    assert otra is not None and otra.orden_fases == ["R", "S", "T"]


def test_facturas_mutadas_no_corrompen_la_cache(tmp_path):
    _escribir(tmp_path / "facturas_distribuidora.yml", "facturas:\n  - planta_id: p1\n")
    loaders.cargar_facturas_distribuidora(str(tmp_path))[0]["planta_id"] = "otra"
    assert loaders.cargar_facturas_distribuidora(str(tmp_path)) == [{"planta_id": "p1"}]

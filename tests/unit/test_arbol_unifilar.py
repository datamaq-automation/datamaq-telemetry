"""tests/unit/test_arbol_unifilar.py — Árbol del unifilar: validación y medidores frontera."""

import pytest

from src.domain.telemetria.entities import NodoUnifilar
from src.domain.telemetria.exceptions import (
    EstructuraUnifilarInvalidaError,
    NodoUnifilarNoEncontradoError,
)
from src.domain.telemetria.servicios.arbol_unifilar import ArbolUnifilarService
from src.domain.telemetria.value_objects import TipoNodoUnifilar


def _nodo(id_: str, parent_id: str | None = None, device_id: str | None = None, orden: int = 0) -> NodoUnifilar:
    return NodoUnifilar(
        id=id_,
        planta_id="planta-1",
        nombre=id_,
        tipo=TipoNodoUnifilar.CARGA,
        tension_nominal_v=380.0,
        parent_id=parent_id,
        device_id=device_id,
        orden=orden,
    )


class TestMedidoresFrontera:
    def test_nodo_medido_devuelve_solo_su_propio_medidor(self):
        arbol = ArbolUnifilarService([_nodo("mt"), _nodo("trafo", parent_id="mt", device_id="dev-1")])
        assert arbol.medidores_frontera("trafo") == ["dev-1"]

    def test_nodo_virtual_suma_sus_hijos_medidos(self):
        arbol = ArbolUnifilarService(
            [
                _nodo("mt"),
                _nodo("trafo-1", parent_id="mt", device_id="dev-1", orden=0),
                _nodo("trafo-2", parent_id="mt", device_id="dev-2", orden=1),
            ]
        )
        assert arbol.medidores_frontera("mt") == ["dev-1", "dev-2"]

    def test_submedicion_anidada_no_se_duplica(self):
        arbol = ArbolUnifilarService(
            [
                _nodo("mt"),
                _nodo("trafo", parent_id="mt", device_id="dev-trafo"),
                _nodo("carga", parent_id="trafo", device_id="dev-carga"),
            ]
        )
        assert arbol.medidores_frontera("mt") == ["dev-trafo"]

    def test_atraviesa_nodos_virtuales_intermedios(self):
        arbol = ArbolUnifilarService(
            [
                _nodo("mt"),
                _nodo("tgbt", parent_id="mt"),
                _nodo("carga", parent_id="tgbt", device_id="dev-carga"),
            ]
        )
        assert arbol.medidores_frontera("mt") == ["dev-carga"]

    def test_nodo_virtual_sin_medidores_devuelve_lista_vacia(self):
        arbol = ArbolUnifilarService([_nodo("mt"), _nodo("tgbt", parent_id="mt")])
        assert arbol.medidores_frontera("mt") == []

    def test_nodo_inexistente_lanza_error(self):
        arbol = ArbolUnifilarService([_nodo("mt")])
        with pytest.raises(NodoUnifilarNoEncontradoError):
            arbol.medidores_frontera("no-existe")

    def test_ciclo_no_cuelga_la_navegacion(self):
        arbol = ArbolUnifilarService([_nodo("a", parent_id="b"), _nodo("b", parent_id="a")])
        assert arbol.medidores_frontera("a") == []


class TestValidar:
    def test_arbol_valido_no_lanza(self):
        ArbolUnifilarService([_nodo("mt"), _nodo("trafo", parent_id="mt", device_id="dev-1")]).validar()

    def test_id_duplicado(self):
        with pytest.raises(EstructuraUnifilarInvalidaError):
            ArbolUnifilarService([_nodo("mt"), _nodo("mt")]).validar()

    def test_padre_colgante(self):
        with pytest.raises(EstructuraUnifilarInvalidaError):
            ArbolUnifilarService([_nodo("trafo", parent_id="no-existe")]).validar()

    def test_auto_padre(self):
        with pytest.raises(EstructuraUnifilarInvalidaError):
            ArbolUnifilarService([_nodo("a", parent_id="a")]).validar()

    def test_ciclo(self):
        with pytest.raises(EstructuraUnifilarInvalidaError):
            ArbolUnifilarService([_nodo("a", parent_id="b"), _nodo("b", parent_id="a")]).validar()

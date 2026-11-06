"""tests/unit/test_arbol_unifilar_duplicados.py — Test para detectar duplicados en frontera."""

import pytest

from src.domain.telemetria.entities import NodoUnifilar
from src.domain.telemetria.exceptions import EstructuraUnifilarInvalidaError
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


class TestDuplicadosEnFrontera:
    """Verificar que nodos_medidores_frontera() nunca devuelve duplicados, incluso si la entrada los tiene."""

    def test_nodos_duplicados_en_entrada_no_generan_duplicados_en_frontera(self):
        """Si la entrada tiene dos nodos con el mismo ID (bug en parser), frontera no debe duplicarlos."""
        # Esto simula un bug donde el parser YAML devuelve dos instancias del mismo nodo
        nodo_mt = _nodo("mt")
        nodo_trafo = _nodo("trafo", parent_id="mt", device_id="dev-1", orden=0)
        nodo_trafo_duplicado = _nodo("trafo", parent_id="mt", device_id="dev-1", orden=0)  # Mismo ID

        arbol = ArbolUnifilarService([nodo_mt, nodo_trafo, nodo_trafo_duplicado])
        frontera = arbol.nodos_medidores_frontera("mt")

        # Extraer device_ids
        device_ids = [n.device_id for n in frontera if n.device_id]

        # Nunca debe haber duplicados en device_ids
        assert len(device_ids) == len(set(device_ids)), f"Hay duplicados en frontera: {device_ids}"
        assert device_ids == ["dev-1"]

    def test_resultado_medidores_nunca_tiene_duplicados(self):
        """Test que verifica medidores_frontera() también."""
        nodo_mt = _nodo("mt")
        nodo_trafo = _nodo("trafo", parent_id="mt", device_id="dev-1")
        nodo_trafo_dup = _nodo("trafo", parent_id="mt", device_id="dev-1")

        arbol = ArbolUnifilarService([nodo_mt, nodo_trafo, nodo_trafo_dup])
        medidores = arbol.medidores_frontera("mt")

        # Lista sin duplicados
        assert len(medidores) == len(set(medidores))
        assert medidores == ["dev-1"]

    def test_dos_nodos_diferentes_mismo_device_id_no_se_deduplican_en_silencio(self):
        """Dos nodos DIFERENTES con el MISMO device_id son error de configuración (datamaq#147).

        medidores_frontera() ya no oculta la repetición: la devuelve tal cual y validar() la rechaza.
        Deduplicar aquí sumaría dos veces el mismo medidor sin dejar rastro.
        """
        nodo_mt = _nodo("mt")
        nodo_trafo_a = _nodo("trafo-a", parent_id="mt", device_id="dev-1", orden=0)
        nodo_trafo_b = _nodo("trafo-b", parent_id="mt", device_id="dev-1", orden=1)

        arbol = ArbolUnifilarService([nodo_mt, nodo_trafo_a, nodo_trafo_b])

        assert arbol.medidores_frontera("mt") == ["dev-1", "dev-1"]
        with pytest.raises(EstructuraUnifilarInvalidaError):
            arbol.validar()

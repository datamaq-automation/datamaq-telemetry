"""tests/unit/test_relacion_transformacion_datos_reales.py.

Invariante sobre el modelo declarativo real (`data/organizaciones.yml`): todo nodo
en MT cuyos medidores frontera estén en BT tiene que derivar un factor de escalado
mayor que 1. Si no, el resumen de ese nodo devuelve `nivel_tension="MT"` junto a
voltajes en escala BT — la anomalía observada en `nodo-durax-acometida-mt`.

Es el test que impide que la próxima planta cargada sin `relacion_tension_kv`
reintroduzca el bug: acá no hay mocks, se lee el YAML que se despliega.
"""

import pytest

from src.domain.telemetria.servicios.arbol_unifilar import ArbolUnifilarService
from src.domain.telemetria.servicios.clasificador_nivel_tension import clasificar_nivel_tension
from src.domain.telemetria.servicios.relacion_transformacion import derivar_relacion_transformacion
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository


def _nodos_mt_con_frontera_bt():
    """(planta_id, nodo, nodos_frontera) de cada nodo MT medido desde BT en el YAML real."""
    repo = YamlOrganizacionesRepository()
    casos = []
    for planta in repo.listar_plantas():
        nodos = repo.obtener_nodos_unifilar(planta.id)
        if not nodos:
            continue
        arbol = ArbolUnifilarService(nodos)
        for nodo in nodos:
            if clasificar_nivel_tension(nodo.tension_nominal_v) != "MT":
                continue
            frontera = arbol.nodos_medidores_frontera(nodo.id)
            if frontera and all(clasificar_nivel_tension(f.tension_nominal_v) == "BT" for f in frontera):
                casos.append(pytest.param(planta.id, nodo, frontera, id=nodo.id))
    return casos


CASOS_MT = _nodos_mt_con_frontera_bt()


def test_el_yaml_declara_al_menos_un_nodo_mt_medido_desde_bt():
    """Guarda del guarda: si el YAML dejara de tener acometidas MT, la
    parametrización de abajo pasaría por vacía y la invariante no probaría nada."""
    assert CASOS_MT, "Ninguna planta declara un nodo MT con medidores frontera en BT"


@pytest.mark.parametrize(("planta_id", "nodo", "frontera"), CASOS_MT)
def test_todo_nodo_mt_medido_desde_bt_deriva_un_factor_de_escala(planta_id, nodo, frontera):
    relacion = derivar_relacion_transformacion(nodo, frontera)

    assert relacion.factor > 1.0, (
        f"El nodo MT '{nodo.id}' (planta {planta_id}, {nodo.tension_nominal_v} V) mide desde "
        f"BT pero deriva factor {relacion.factor} (origen={relacion.origen}): su resumen "
        f"devolvería nivel_tension='MT' con voltajes en escala BT."
    )

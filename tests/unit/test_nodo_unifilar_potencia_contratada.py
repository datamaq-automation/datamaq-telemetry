"""tests/unit/test_nodo_unifilar_potencia_contratada.py

Pruebas unitarias para el soporte GitOps de potencia contratada en nodos unifilar (acometida).
"""

from src.infrastructure.yaml.repositories.organizaciones_repository import (
    YamlOrganizacionesRepository,
    _parsear_nodo_unifilar,
)


def test_parsear_nodo_unifilar_con_franjas_diferenciadas():
    nodo_dict = {
        "id": "nodo-acometida-1",
        "nombre": "Acometida MT",
        "tipo": "acometida",
        "tension_nominal_v": 13200.0,
        "potencia_contratada_punta_kw": 800.0,
        "potencia_contratada_fuera_punta_kw": 850.0,
    }

    nodo = _parsear_nodo_unifilar(nodo_dict, planta_id="planta-1")
    assert nodo.potencia_contratada_punta_kw == 800.0
    assert nodo.potencia_contratada_fuera_punta_kw == 850.0


def test_parsear_nodo_unifilar_con_potencia_contratada_kw_unica_replica_en_ambas_franjas():
    # Si solo se declara potencia_contratada_kw, se replica en ambas franjas según spec
    nodo_dict = {
        "id": "nodo-acometida-2",
        "nombre": "Acometida BT",
        "tipo": "acometida",
        "tension_nominal_v": 380.0,
        "potencia_contratada_kw": 250.0,
    }

    nodo = _parsear_nodo_unifilar(nodo_dict, planta_id="planta-2")
    assert nodo.potencia_contratada_punta_kw == 250.0
    assert nodo.potencia_contratada_fuera_punta_kw == 250.0


def test_parsear_nodo_unifilar_sin_potencia_contratada():
    nodo_dict = {
        "id": "nodo-maquina-1",
        "nombre": "Motor 1",
        "tipo": "maquina",
        "tension_nominal_v": 380.0,
    }

    nodo = _parsear_nodo_unifilar(nodo_dict, planta_id="planta-3")
    assert nodo.potencia_contratada_punta_kw is None
    assert nodo.potencia_contratada_fuera_punta_kw is None


def test_carga_desde_organizaciones_yml_real():
    repo = YamlOrganizacionesRepository(data_dir="data")
    nodos_durax = repo.obtener_nodos_unifilar("c64fd625-0037-4caa-b68a-800e8e0ee548")
    acometida_durax = next((n for n in nodos_durax if n.id == "nodo-durax-acometida-mt"), None)
    assert acometida_durax is not None
    assert acometida_durax.potencia_contratada_punta_kw == 800.0
    assert acometida_durax.potencia_contratada_fuera_punta_kw == 850.0

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
        "id": "nodo-carga-1",
        "nombre": "Motor 1",
        "tipo": "carga",
        "tension_nominal_v": 380.0,
    }

    nodo = _parsear_nodo_unifilar(nodo_dict, planta_id="planta-3")
    assert nodo.potencia_contratada_punta_kw is None
    assert nodo.potencia_contratada_fuera_punta_kw is None


def test_carga_desde_organizaciones_yml_real():
    repo = YamlOrganizacionesRepository(data_dir="data")
    nodos_durax = repo.obtener_nodos_unifilar("c64fd625-0037-4caa-b68a-800e8e0ee548")
    acometida_durax = next((n for n in nodos_durax if n.id == "node-durax-principal-acometida-1"), None)
    assert acometida_durax is not None
    assert acometida_durax.potencia_contratada_punta_kw == 848.4
    assert acometida_durax.potencia_contratada_fuera_punta_kw == 848.4


def _acometida(**extra: object) -> dict:
    base: dict = {
        "id": "acometida-test",
        "nombre": "Acometida test",
        "tipo": "acometida",
        "tension_nominal_v": 13200.0,
    }
    base.update(extra)
    return base


def test_esquema_potencia_sin_declarar_es_por_franja():
    from src.domain.telemetria.value_objects import EsquemaPotencia

    nodo = _parsear_nodo_unifilar(_acometida(), planta_id="planta-1")
    assert nodo.esquema_potencia is EsquemaPotencia.POR_FRANJA
    assert nodo.capacidad_convenida_kw is None


def test_esquema_capacidad_unica_con_capacidad_convenida():
    from src.domain.telemetria.value_objects import EsquemaPotencia

    nodo = _parsear_nodo_unifilar(
        _acometida(esquema_potencia="capacidad_unica", capacidad_convenida_kw=848.4),
        planta_id="planta-1",
    )
    assert nodo.esquema_potencia is EsquemaPotencia.CAPACIDAD_UNICA
    assert nodo.capacidad_convenida_kw == 848.4


def test_esquema_por_franja_explicito_con_franjas():
    from src.domain.telemetria.value_objects import EsquemaPotencia

    nodo = _parsear_nodo_unifilar(
        _acometida(esquema_potencia="por_franja", potencia_contratada_punta_kw=800.0),
        planta_id="planta-1",
    )
    assert nodo.esquema_potencia is EsquemaPotencia.POR_FRANJA
    assert nodo.potencia_contratada_punta_kw == 800.0


def test_esquema_desconocido_falla_con_nombre_del_nodo():
    import re

    import pytest

    with pytest.raises(
        ValueError, match=re.escape("nodo 'acometida-test': esquema_potencia 'tarifa_rara' no reconocido")
    ):
        _parsear_nodo_unifilar(_acometida(esquema_potencia="tarifa_rara"), planta_id="planta-1")


def test_capacidad_unica_sin_capacidad_convenida_falla():
    import pytest

    with pytest.raises(ValueError, match="capacidad_unica requiere capacidad_convenida_kw > 0"):
        _parsear_nodo_unifilar(_acometida(esquema_potencia="capacidad_unica"), planta_id="planta-1")


def test_capacidad_unica_con_capacidad_cero_falla():
    import pytest

    with pytest.raises(ValueError, match="requiere capacidad_convenida_kw > 0"):
        _parsear_nodo_unifilar(
            _acometida(esquema_potencia="capacidad_unica", capacidad_convenida_kw=0),
            planta_id="planta-1",
        )


def test_capacidad_convenida_con_por_franja_falla_para_no_ignorarla_en_silencio():
    import pytest

    with pytest.raises(ValueError, match="solo aplica con esquema capacidad_unica"):
        _parsear_nodo_unifilar(
            _acometida(esquema_potencia="por_franja", capacidad_convenida_kw=848.4),
            planta_id="planta-1",
        )

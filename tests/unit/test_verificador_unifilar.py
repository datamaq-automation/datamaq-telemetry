"""tests/unit/test_verificador_unifilar.py — validación del unifilar del YAML en startup."""

from unittest.mock import MagicMock

from src.domain.telemetria.entities import NodoUnifilar, Planta
from src.domain.telemetria.value_objects import TipoNodoUnifilar
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository
from src.infrastructure.yaml.verificador_unifilar import verificar_unifilar_plantas


def _nodo(id_: str, parent_id: str | None = None) -> NodoUnifilar:
    return NodoUnifilar(
        id=id_, planta_id="p", nombre=id_, tipo=TipoNodoUnifilar.CARGA, tension_nominal_v=380.0, parent_id=parent_id
    )


def test_yaml_real_del_repo_es_valido():
    resultado = verificar_unifilar_plantas(YamlOrganizacionesRepository(data_dir="data"))
    assert resultado["plantas"] >= 3
    assert resultado["invalidas"] == 0


def test_planta_con_ciclo_se_reporta_sin_bloquear():
    repo = MagicMock()
    repo.listar_plantas.return_value = [
        Planta(id="ok", organizacion_id="o", nombre="OK"),
        Planta(id="mal", organizacion_id="o", nombre="Mal"),
    ]
    repo.obtener_nodos_unifilar.side_effect = lambda pid: (
        [_nodo("a"), _nodo("b", "a")] if pid == "ok" else [_nodo("x", "y"), _nodo("y", "x")]
    )
    resultado = verificar_unifilar_plantas(repo)
    assert resultado == {"plantas": 2, "invalidas": 1}

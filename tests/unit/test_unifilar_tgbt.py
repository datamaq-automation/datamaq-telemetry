"""tests/unit/test_unifilar_tgbt.py — R-01/R-03: nivel TGBT, vocabulario cerrado de `tipo` y nombre de máquina."""

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.application.dtos.planta_estructura_dto import NodoUnifilarDTO
from src.application.use_cases.gestionar_planta_estructura import GestionarPlantaEstructuraUseCase
from src.domain.disponibilidad.entities import Maquina
from src.domain.telemetria.entities import NodoUnifilar, Planta
from src.domain.telemetria.servicios.arbol_unifilar import ArbolUnifilarService
from src.domain.telemetria.value_objects import TipoNodoUnifilar
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

PLANTA = Planta(id="planta-1", organizacion_id="org-1", nombre="Planta Test")


def _nodo(id_: str, tipo: TipoNodoUnifilar, parent_id: str | None = None, device_id: str | None = None):
    return NodoUnifilar(
        id=id_,
        planta_id="planta-1",
        nombre=id_,
        tipo=tipo,
        tension_nominal_v=380.0,
        parent_id=parent_id,
        device_id=device_id,
    )


def _repo_org(nodos: list[NodoUnifilar]) -> MagicMock:
    repo = MagicMock()
    repo.obtener_planta_por_id.return_value = PLANTA
    repo.obtener_nodos_unifilar.return_value = nodos
    return repo


# --- Vocabulario cerrado de `tipo` (R-01) ---


def test_dto_acepta_solo_tipos_del_vocabulario():
    for tipo in ("acometida", "transformador", "tgbt", "seccional", "maquina"):
        assert NodoUnifilarDTO(id="n", nombre="n", tipo=tipo, tension_nominal_V=380.0).tipo == tipo
    with pytest.raises(ValidationError):
        NodoUnifilarDTO(id="n", nombre="n", tipo="alimentador", tension_nominal_V=380.0)


# --- Nivel de tensión MT/BT derivado (respuesta a pregunta 3 del frontend) ---


def test_obtener_unifilar_deriva_nivel_tension_mt_bt():
    nodos = [
        NodoUnifilar(
            id="mt", planta_id="planta-1", nombre="mt", tipo=TipoNodoUnifilar.ACOMETIDA, tension_nominal_v=13200.0
        ),
        NodoUnifilar(
            id="bt",
            planta_id="planta-1",
            nombre="bt",
            tipo=TipoNodoUnifilar.TGBT,
            tension_nominal_v=380.0,
            parent_id="mt",
            device_id="dev-1",
        ),
    ]
    res = GestionarPlantaEstructuraUseCase(_repo_org(nodos)).obtener_unifilar("planta-1")
    por_id = {n.id: n for n in res.nodos}
    assert por_id["mt"].nivel_tension == "MT"
    assert por_id["bt"].nivel_tension == "BT"


# --- topologia_valida (respuesta a pregunta 1 del frontend: señal de estructura completa) ---


def test_unifilar_topologia_valida_false_si_hay_padre_colgante():
    nodos = [
        _nodo("hijo", TipoNodoUnifilar.TGBT, parent_id="padre-inexistente", device_id="dev-1"),
    ]
    res = GestionarPlantaEstructuraUseCase(_repo_org(nodos)).obtener_unifilar("planta-1")
    assert res.topologia_valida is False


def test_unifilar_topologia_valida_true_si_arbol_es_consistente():
    nodos = [_nodo("mt", TipoNodoUnifilar.ACOMETIDA, device_id="dev-1")]
    res = GestionarPlantaEstructuraUseCase(_repo_org(nodos)).obtener_unifilar("planta-1")
    assert res.topologia_valida is True


# --- Nombre de máquina en el nodo medido (R-03) ---


def test_obtener_unifilar_incluye_nombre_maquina_solo_en_nodos_medidos():
    nodos = [
        _nodo("mt", TipoNodoUnifilar.ACOMETIDA),
        _nodo("trafo", TipoNodoUnifilar.TRANSFORMADOR, parent_id="mt"),
        _nodo("tgbt", TipoNodoUnifilar.TGBT, parent_id="trafo", device_id="dev-1"),
        _nodo("tgbt-sin-maquina", TipoNodoUnifilar.TGBT, parent_id="trafo", device_id="dev-2"),
    ]
    repo_maquinas = MagicMock()
    repo_maquinas.listar.return_value = [Maquina(id="m-1", dispositivo_id="dev-1", nombre="Inyectora 1")]
    use_case = GestionarPlantaEstructuraUseCase(_repo_org(nodos), repo_maquinas)

    res = use_case.obtener_unifilar("planta-1")

    por_id = {n.id: n for n in res.nodos}
    assert por_id["tgbt"].nombre_maquina == "Inyectora 1"
    assert por_id["tgbt-sin-maquina"].nombre_maquina is None
    assert por_id["trafo"].nombre_maquina is None and por_id["trafo"].es_virtual is True
    repo_maquinas.listar.assert_called_once_with("org-1")


def test_obtener_unifilar_sin_repo_maquinas_no_consulta_nada():
    nodos = [_nodo("mt", TipoNodoUnifilar.ACOMETIDA, device_id="dev-1")]
    res = GestionarPlantaEstructuraUseCase(_repo_org(nodos)).obtener_unifilar("planta-1")
    assert res.nodos[0].nombre_maquina is None


def test_obtener_unifilar_sin_nodos_medidos_no_consulta_maquinas():
    repo_maquinas = MagicMock()
    nodos = [_nodo("mt", TipoNodoUnifilar.ACOMETIDA)]
    GestionarPlantaEstructuraUseCase(_repo_org(nodos), repo_maquinas).obtener_unifilar("planta-1")
    repo_maquinas.listar.assert_not_called()


# --- Topología declarativa real: TGBT como punto de medición aguas abajo del trafo ---


@pytest.mark.parametrize(
    "planta_id",
    ["c64fd625-0037-4caa-b68a-800e8e0ee548", "4f68f653-a604-4834-8154-31f938248572"],  # Durax, UPP
)
def test_yaml_plantas_industriales_miden_en_el_tgbt(planta_id: str):
    nodos = YamlOrganizacionesRepository(data_dir="data").obtener_nodos_unifilar(planta_id)
    arbol = ArbolUnifilarService(nodos)
    arbol.validar()

    por_tipo: dict[TipoNodoUnifilar, list[NodoUnifilar]] = {}
    for n in nodos:
        por_tipo.setdefault(n.tipo, []).append(n)

    assert len(por_tipo[TipoNodoUnifilar.TGBT]) == 2
    assert all(n.device_id for n in por_tipo[TipoNodoUnifilar.TGBT])
    assert all(n.device_id is None for n in por_tipo[TipoNodoUnifilar.TRANSFORMADOR])
    assert all(n.device_id is None for n in por_tipo[TipoNodoUnifilar.ACOMETIDA])
    # Cada TGBT cuelga de un transformador y cada transformador de la acometida MT
    trafos = {n.id for n in por_tipo[TipoNodoUnifilar.TRANSFORMADOR]}
    assert {n.parent_id for n in por_tipo[TipoNodoUnifilar.TGBT]} == trafos
    acometida = por_tipo[TipoNodoUnifilar.ACOMETIDA][0]
    # La acometida MT sigue sumando los dos medidores frontera, ahora ubicados en los TGBT
    assert sorted(arbol.medidores_frontera(acometida.id)) == sorted(
        n.device_id for n in por_tipo[TipoNodoUnifilar.TGBT]
    )


def test_unifilar_dto_v2_metadatos_placa_coordenadas_interruptor():
    dto = NodoUnifilarDTO(
        id="nodo-test",
        parent_id="nodo-padre",
        nombre="TGBT Test",
        tipo="tgbt",
        device_id="dev-1",
        tension_nominal_V=380.0,
        orden=1,
        es_pasante=False,
        coordenadas={"x": 100.0, "y": 200.0, "ancho": 80.0, "orientacion": "horizontal"},
        metadatos_placa={
            "trafo_asociado_kva": 1000.0,
            "corriente_barra_a": 1600.0,
            "icw_ka": 50.0,
            "proteccion_in_a": 1600.0,
            "marca": "Schneider",
        },
        interruptor_cabecera={
            "tag": "Q0",
            "tipo": "ACB",
            "in_a": 1600.0,
            "icu_ka": 65.0,
            "estado": "cerrado",
        },
    )
    assert dto.orden == 1
    assert dto.es_pasante is False
    assert dto.coordenadas is not None and dto.coordenadas.x == 100.0
    assert dto.coordenadas.orientacion == "horizontal"
    assert dto.metadatos_placa is not None
    assert dto.metadatos_placa.trafo_asociado_kva == 1000.0
    assert dto.metadatos_placa.corriente_nominal_a is None
    assert getattr(dto.metadatos_placa, "marca", None) == "Schneider"
    assert dto.interruptor_cabecera is not None
    assert dto.interruptor_cabecera.tag == "Q0"
    assert dto.interruptor_cabecera.in_a == 1600.0


def test_arbol_unifilar_es_nodo_pasante():
    acometida = _nodo("acometida", TipoNodoUnifilar.ACOMETIDA)
    trafo1 = _nodo("trafo1", TipoNodoUnifilar.TRANSFORMADOR, parent_id="acometida")
    trafo2 = _nodo("trafo2", TipoNodoUnifilar.TRANSFORMADOR, parent_id="acometida")
    tgbt1 = _nodo("tgbt1", TipoNodoUnifilar.TGBT, parent_id="trafo1", device_id="dev-1")
    tgbt2 = _nodo("tgbt2", TipoNodoUnifilar.TGBT, parent_id="trafo2", device_id="dev-2")

    arbol = ArbolUnifilarService([acometida, trafo1, trafo2, tgbt1, tgbt2])
    # Acometida tiene 2 hijos -> NO es pasante (es barra de bifurcación)
    assert arbol.es_nodo_pasante("acometida") is False
    # trafo1 y trafo2 son virtuales y tienen exactamente 1 hijo -> SÍ son pasantes
    assert arbol.es_nodo_pasante("trafo1") is True
    assert arbol.es_nodo_pasante("trafo2") is True
    # tgbt1 y tgbt2 tienen medidor -> NO son pasantes
    assert arbol.es_nodo_pasante("tgbt1") is False
    assert arbol.es_nodo_pasante("tgbt2") is False


def test_yaml_durax_incluye_metadatos_placa_y_layout():
    repo = YamlOrganizacionesRepository(data_dir="data")
    nodos = repo.obtener_nodos_unifilar("c64fd625-0037-4caa-b68a-800e8e0ee548")
    por_id = {n.id: n for n in nodos}

    acometida = por_id["node-durax-principal-acometida-1"]
    assert acometida.coordenadas is not None
    assert acometida.coordenadas.orientacion == "horizontal"
    assert acometida.metadatos_placa is not None
    assert acometida.metadatos_placa.tension_nominal_v == 13200.0
    assert acometida.interruptor_cabecera is not None
    assert acometida.interruptor_cabecera.tag == "QM-01"

    trafo_usina = por_id["node-durax-principal-transformacin-2"]
    assert trafo_usina.es_pasante is True
    assert trafo_usina.metadatos_placa is not None
    assert trafo_usina.metadatos_placa.potencia_nominal_kva == 1000.0
    assert trafo_usina.metadatos_placa.grupo_conexion == "Dyn11"

    tgbt_usina = por_id["node-durax-principal-tgbt-4"]
    assert tgbt_usina.es_pasante is False
    assert tgbt_usina.metadatos_placa is not None
    assert tgbt_usina.metadatos_placa.trafo_asociado_kva == 1000.0
    assert tgbt_usina.interruptor_cabecera is not None
    assert tgbt_usina.interruptor_cabecera.tag == "Q0-USINA"
    assert tgbt_usina.interruptor_cabecera.in_a == 1600.0


def test_obtener_unifilar_marca_trafos_pasantes():
    use_case = GestionarPlantaEstructuraUseCase(YamlOrganizacionesRepository(data_dir="data"))
    unifilar = use_case.obtener_unifilar("c64fd625-0037-4caa-b68a-800e8e0ee548")
    por_id = {n.id: n for n in unifilar.nodos}

    assert por_id["node-durax-principal-acometida-1"].es_pasante is False
    assert por_id["node-durax-principal-transformacin-2"].es_pasante is True
    assert por_id["node-durax-principal-transformacin-3"].es_pasante is True
    assert por_id["node-durax-principal-tgbt-4"].es_pasante is False
    assert por_id["node-durax-principal-tgbt-5"].es_pasante is False

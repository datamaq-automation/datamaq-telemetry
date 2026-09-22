"""tests/unit/test_relacion_transformacion.py — Derivación del factor de escalado por nodo."""

import pytest

from src.domain.telemetria.entities import NodoUnifilar
from src.domain.telemetria.servicios.relacion_transformacion import (
    derivar_relacion_transformacion,
    parsear_relacion_placa_kv,
)
from src.domain.telemetria.value_objects import MetadatosPlaca, TipoNodoUnifilar

PLANTA_ID = "planta-test"


def _nodo(
    id_: str,
    tension_nominal_v: float,
    tipo: TipoNodoUnifilar = TipoNodoUnifilar.TGBT,
    placa: str | None = None,
    device_id: str | None = None,
) -> NodoUnifilar:
    return NodoUnifilar(
        id=id_,
        planta_id=PLANTA_ID,
        nombre=id_,
        tipo=tipo,
        tension_nominal_v=tension_nominal_v,
        device_id=device_id,
        metadatos_placa=MetadatosPlaca(relacion_tension_kv=placa) if placa is not None else None,
    )


# --- parsear_relacion_placa_kv ---


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("15/0.4", 37.5),
        ("13.2/0.4", 33.0),
        ("13.2 / 0.4", 33.0),
        ("  13.2 / 0.4  ", 33.0),
        ("13.2 kV / 0.4 kV", 33.0),
        ("13.2 kv / 0.4 kv", 33.0),
        ("13.2 V / 0.4 V", 33.0),
        # Unidades mixtas: el parser es literal sobre los números, no los convierte.
        # El resultado absurdo lo filtra después el contraste contra el árbol.
        ("13.2 kV / 400 V", 0.033),
    ],
)
def test_parsear_relacion_placa_kv_interpreta_las_formas_del_yaml(valor, esperado):
    assert parsear_relacion_placa_kv(valor) == pytest.approx(esperado)


@pytest.mark.parametrize(
    "valor",
    [
        None,
        "",
        "13.2",
        "13.2/",
        "/13.2",
        "13.2/0",
        "13.2/0.0",
        "13.2/0.4/extra",
        "13.2/0.4/0.23",
        "abc/def",
        "Dyn11",
        "kV/kV",
    ],
)
def test_parsear_relacion_placa_kv_devuelve_none_si_no_es_interpretable(valor):
    """Devuelve None, no 1.0: el default lo decide el llamador, que ya no siempre
    es "no escalar" (un nodo MT sin placa escala por el cociente del árbol)."""
    assert parsear_relacion_placa_kv(valor) is None


# --- derivar_relacion_transformacion: precedencia ---


def test_nodo_bt_no_escala_aunque_declare_placa():
    """No-regresión de feca8e7 (caso Durax): un transformador de 380 V declara su
    relación de placa pero se mide en su propia barra BT; ese dato es nameplate,
    no una instrucción de escalar ESTE nodo."""
    nodo = _nodo("trafo-durax", 380.0, TipoNodoUnifilar.TRANSFORMADOR, placa="13.2/0.4")
    frontera = [_nodo("tgbt", 380.0, device_id="dev-1")]

    relacion = derivar_relacion_transformacion(nodo, frontera)

    assert relacion.factor == 1.0
    assert relacion.origen == "nodo_bt"
    assert relacion.advertencia is None


def test_nodo_mt_sin_placa_usa_el_cociente_de_nominales_del_arbol():
    """Caso `nodo-durax-acometida-mt`: 13.2 kV sin `relacion_tension_kv` declarada."""
    nodo = _nodo("acometida-durax", 13200.0, TipoNodoUnifilar.ACOMETIDA)
    frontera = [_nodo("tgbt-1", 380.0, device_id="dev-1"), _nodo("tgbt-2", 380.0, device_id="dev-2")]

    relacion = derivar_relacion_transformacion(nodo, frontera)

    assert round(relacion.factor, 4) == round(13200.0 / 380.0, 4)
    assert relacion.origen == "cociente_nominales"
    assert relacion.advertencia is None


def test_nodo_mt_con_placa_coherente_prefiere_la_placa():
    """Caso `nodo-upp-acometida-mt`: la placa (33.0) queda dentro de la tolerancia
    frente al cociente del árbol (34.74) y gana por ser el turns ratio real."""
    nodo = _nodo("acometida-upp", 13200.0, TipoNodoUnifilar.ACOMETIDA, placa="13.2/0.4")
    frontera = [_nodo("tgbt", 380.0, device_id="dev-1")]

    relacion = derivar_relacion_transformacion(nodo, frontera)

    assert relacion.factor == pytest.approx(33.0)
    assert relacion.origen == "placa"
    assert relacion.advertencia is None


def test_nodo_mt_con_placa_incoherente_usa_el_arbol_y_advierte():
    """Una placa copiada de otro equipo (33 kV/0.4 → 82.5) no debe multiplicar por
    el doble lo que el árbol dice que es una relación de ~34.7."""
    nodo = _nodo("acometida", 13200.0, TipoNodoUnifilar.ACOMETIDA, placa="33/0.4")
    frontera = [_nodo("tgbt", 380.0, device_id="dev-1")]

    relacion = derivar_relacion_transformacion(nodo, frontera)

    assert round(relacion.factor, 4) == round(13200.0 / 380.0, 4)
    assert relacion.origen == "cociente_nominales"
    assert relacion.advertencia is not None


def test_frontera_ya_en_mt_no_escala_aunque_haya_placa():
    """Un medidor de MT real sobre la acometida: el agregado ya está en la escala
    del nodo. Es la red de seguridad que el string de placa por sí solo no da."""
    nodo = _nodo("acometida", 13200.0, TipoNodoUnifilar.ACOMETIDA, placa="13.2/0.4")
    frontera = [_nodo("medidor-mt", 13200.0, device_id="dev-1")]

    relacion = derivar_relacion_transformacion(nodo, frontera)

    assert relacion.factor == 1.0
    assert relacion.origen == "medicion_en_nivel_del_nodo"


def test_frontera_heterogenea_no_escala_y_advierte():
    """Medidores frontera en niveles distintos: un escalar único no los representa."""
    nodo = _nodo("acometida", 13200.0, TipoNodoUnifilar.ACOMETIDA)
    frontera = [_nodo("tgbt", 380.0, device_id="dev-1"), _nodo("barra-220", 220.0, device_id="dev-2")]

    relacion = derivar_relacion_transformacion(nodo, frontera)

    assert relacion.factor == 1.0
    assert relacion.origen == "frontera_heterogenea"
    assert relacion.advertencia is not None


def test_nodo_mt_sin_frontera_ni_placa_no_escala_y_advierte():
    nodo = _nodo("acometida-huerfana", 13200.0, TipoNodoUnifilar.ACOMETIDA)

    relacion = derivar_relacion_transformacion(nodo, [])

    assert relacion.factor == 1.0
    assert relacion.origen == "sin_frontera"
    assert relacion.advertencia is not None


def test_nodo_mt_sin_frontera_con_placa_usa_la_placa():
    """Sin árbol contra el cual contrastar, la placa es el único dato disponible."""
    nodo = _nodo("acometida", 13200.0, TipoNodoUnifilar.ACOMETIDA, placa="13.2/0.4")

    relacion = derivar_relacion_transformacion(nodo, [])

    assert relacion.factor == pytest.approx(33.0)
    assert relacion.origen == "placa"

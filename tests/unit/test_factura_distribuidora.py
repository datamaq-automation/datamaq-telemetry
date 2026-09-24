"""tests/unit/test_factura_distribuidora.py — Entidad FacturaDistribuidora y su repositorio YAML."""

import dataclasses

import pytest
import yaml

from src.domain.sge.entities import FacturaDistribuidora
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

PLANTA_A = "planta-a"
PLANTA_B = "planta-b"


def _factura(**overrides) -> FacturaDistribuidora:
    """Factura con ambos tipos de campo poblados, solo para probar cómodamente las properties
    calculadas — un documento real trae uno u otro, nunca los dos (ver `tipo_dato`)."""
    base = dict(
        id="planta-a-2026-08-potencia",
        planta_id=PLANTA_A,
        periodo="2026-08",
        proveedor="EDELAP",
        tipo_dato="potencia",
        numero_factura="0020-01988580",
        importe_total_ars=21031736.78,
        tarifa="T5M12",
        dias_facturados=30,
        energia_activa_punta_kwh=68310.0,
        energia_activa_resto_kwh=187506.0,
        energia_activa_valle_kwh=59994.0,
        potencia_contratada_punta_kw=800.0,
        potencia_contratada_fuera_punta_kw=850.0,
        potencia_adquirida_punta_kw=1049.0,
        potencia_adquirida_fuera_punta_kw=1082.0,
        importe_potencia_ars=7664856.62,
        importe_energia_ars=638572.35,
    )
    base.update(overrides)
    return FacturaDistribuidora(**base)


def test_es_frozen():
    factura = _factura()
    with pytest.raises(dataclasses.FrozenInstanceError):
        factura.periodo = "2026-09"  # type: ignore[misc]


def test_energia_facturada_kwh_suma_las_tres_franjas():
    factura = _factura()
    assert factura.energia_facturada_kwh == pytest.approx(68310.0 + 187506.0 + 59994.0)
    assert factura.energia_facturada_kwh == pytest.approx(315810.0)


def test_energia_facturada_kwh_none_si_falta_alguna_franja():
    factura = _factura(energia_activa_valle_kwh=None)
    assert factura.energia_facturada_kwh is None


def test_potencia_excedida_punta_y_fuera_punta():
    factura = _factura()
    assert factura.potencia_excedida_punta_kw == pytest.approx(249.0)
    assert factura.potencia_excedida_fuera_punta_kw == pytest.approx(232.0)


def test_potencia_excedida_none_si_falta_dato_de_potencia():
    factura = _factura(potencia_adquirida_punta_kw=None)
    assert factura.potencia_excedida_punta_kw is None


def test_potencia_excedida_no_negativa_cuando_adquirida_menor_a_contratada():
    factura = _factura(potencia_adquirida_punta_kw=500.0, potencia_contratada_punta_kw=800.0)
    assert factura.potencia_excedida_punta_kw == 0.0


def test_valor_energia_ars_kwh_promedio():
    factura = _factura()
    esperado = 638572.35 / 315810.0
    assert factura.valor_energia_ars_kwh_promedio == pytest.approx(esperado)


def test_valor_energia_ars_kwh_promedio_sin_energia_no_divide_por_cero():
    factura = _factura(
        energia_activa_punta_kwh=0.0,
        energia_activa_resto_kwh=0.0,
        energia_activa_valle_kwh=0.0,
    )
    assert factura.valor_energia_ars_kwh_promedio is None


def test_valor_energia_ars_kwh_promedio_none_si_falta_importe():
    factura = _factura(importe_energia_ars=None)
    assert factura.valor_energia_ars_kwh_promedio is None


def test_factura_solo_potencia_deja_campos_de_energia_en_none():
    """Un documento real de un solo tipo (ej. potencia de EdeLAP) no trae energía."""
    factura = FacturaDistribuidora(
        id="planta-a-2026-08-potencia",
        planta_id=PLANTA_A,
        periodo="2026-08",
        proveedor="EDELAP",
        tipo_dato="potencia",
        numero_factura="0020-01988580",
        importe_total_ars=7664856.62,
        potencia_contratada_punta_kw=800.0,
        potencia_adquirida_punta_kw=1049.0,
    )
    assert factura.energia_facturada_kwh is None
    assert factura.valor_energia_ars_kwh_promedio is None
    assert factura.potencia_excedida_punta_kw == pytest.approx(249.0)


@pytest.fixture
def data_dir(tmp_path):
    contenido = {
        "facturas": [
            {
                "planta_id": PLANTA_A,
                "periodo": "2026-07",
                "proveedor": "EDELAP",
                "tipo_dato": "potencia",
                "numero_factura": "f-a-07",
                "importe_total_ars": 100.0,
            },
            {
                "planta_id": PLANTA_A,
                "periodo": "2026-08",
                "proveedor": "EDELAP",
                "tipo_dato": "potencia",
                "numero_factura": "f-a-08-p",
                "importe_total_ars": 200.0,
            },
            {
                "planta_id": PLANTA_A,
                "periodo": "2026-08",
                "proveedor": "CAMMESA",
                "tipo_dato": "energia",
                "numero_factura": "f-a-08-e",
                "importe_total_ars": 50.0,
                "energia_activa_punta_kwh": 999.0,
            },
            {
                "planta_id": PLANTA_B,
                "periodo": "2026-08",
                "proveedor": "EDELAP",
                "tipo_dato": "potencia",
                "numero_factura": "f-b-08",
                "importe_total_ars": 999.0,
            },
        ]
    }
    (tmp_path / "facturas_distribuidora.yml").write_text(yaml.safe_dump(contenido), encoding="utf-8")
    return str(tmp_path)


def test_obtener_facturas_planta_orden_descendente_por_periodo(data_dir):
    repo = YamlOrganizacionesRepository(data_dir=data_dir)
    facturas = repo.obtener_facturas_planta(PLANTA_A)
    assert [f.periodo for f in facturas] == ["2026-08", "2026-08", "2026-07"]


def test_obtener_facturas_planta_dos_documentos_mismo_periodo(data_dir):
    repo = YamlOrganizacionesRepository(data_dir=data_dir)
    facturas = repo.obtener_facturas_planta(PLANTA_A)
    del_periodo = [f for f in facturas if f.periodo == "2026-08"]
    assert {f.tipo_dato for f in del_periodo} == {"potencia", "energia"}


def test_obtener_facturas_planta_filtra_por_planta(data_dir):
    repo = YamlOrganizacionesRepository(data_dir=data_dir)
    facturas = repo.obtener_facturas_planta(PLANTA_B)
    assert len(facturas) == 1
    assert facturas[0].importe_total_ars == 999.0


def test_obtener_facturas_planta_sin_facturas_devuelve_lista_vacia(data_dir):
    repo = YamlOrganizacionesRepository(data_dir=data_dir)
    assert repo.obtener_facturas_planta("planta-inexistente") == []


def test_obtener_facturas_planta_sin_archivo_devuelve_lista_vacia(tmp_path):
    repo = YamlOrganizacionesRepository(data_dir=str(tmp_path))
    assert repo.obtener_facturas_planta(PLANTA_A) == []

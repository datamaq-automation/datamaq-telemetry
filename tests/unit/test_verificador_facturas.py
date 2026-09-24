"""tests/unit/test_verificador_facturas.py — Validador de integridad del histórico de facturas."""

from unittest.mock import MagicMock

from src.domain.sge.entities import FacturaDistribuidora
from src.domain.telemetria.entities import Planta
from src.infrastructure.yaml.verificador_facturas import verificar_facturas_plantas

PLANTA_ID = "planta-x"


def _factura(**overrides) -> FacturaDistribuidora:
    base = dict(
        id="f1",
        planta_id=PLANTA_ID,
        periodo="2026-08",
        proveedor="EDELAP",
        tipo_dato="potencia",
        numero_factura="1",
        importe_total_ars=100.0,
        tarifa="T5M12",
        dias_facturados=30,
        potencia_contratada_punta_kw=100.0,
        potencia_contratada_fuera_punta_kw=100.0,
        potencia_adquirida_punta_kw=100.0,
        potencia_adquirida_fuera_punta_kw=100.0,
        importe_potencia_ars=100.0,
    )
    base.update(overrides)
    return FacturaDistribuidora(**base)


def _repo(facturas: list[FacturaDistribuidora]) -> MagicMock:
    repo = MagicMock()
    repo.listar_plantas.return_value = [Planta(id=PLANTA_ID, organizacion_id="org-x", nombre="Planta X")]
    repo.obtener_facturas_planta.return_value = facturas
    return repo


def test_facturas_validas_no_reporta_invalidas():
    repo = _repo([_factura(periodo="2026-07"), _factura(periodo="2026-08")])
    resultado = verificar_facturas_plantas(repo)
    assert resultado == {"plantas": 1, "invalidas": 0}


def test_periodo_duplicado_en_la_misma_planta_es_invalido():
    repo = _repo(
        [
            _factura(id="f1", periodo="2026-08", tipo_dato="potencia"),
            _factura(id="f2", periodo="2026-08", tipo_dato="potencia"),
        ]
    )
    resultado = verificar_facturas_plantas(repo)
    assert resultado["invalidas"] == 1


def test_mismo_periodo_con_distinto_tipo_dato_no_es_duplicado():
    """UPP: EdeLAP factura potencia y CAMMESA factura energía del mismo período — no es
    un duplicado, son dos documentos distintos."""
    repo = _repo(
        [
            _factura(id="f1", periodo="2026-08", tipo_dato="potencia"),
            _factura(id="f2", periodo="2026-08", tipo_dato="energia"),
        ]
    )
    resultado = verificar_facturas_plantas(repo)
    assert resultado["invalidas"] == 0


def test_formato_de_periodo_invalido():
    repo = _repo([_factura(periodo="agosto-2026")])
    resultado = verificar_facturas_plantas(repo)
    assert resultado["invalidas"] == 1


def test_magnitud_negativa_es_invalida():
    repo = _repo([_factura(importe_total_ars=-1.0)])
    resultado = verificar_facturas_plantas(repo)
    assert resultado["invalidas"] == 1


def test_planta_sin_facturas_no_reporta_invalidas():
    repo = _repo([])
    resultado = verificar_facturas_plantas(repo)
    assert resultado == {"plantas": 1, "invalidas": 0}

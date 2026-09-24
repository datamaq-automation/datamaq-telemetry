"""tests/unit/test_parser_factura_distribuidora.py — Parser de facturas PDF con pdfplumber.

El PDF de fixture usa un layout simple "Etiqueta: valor" que el parser sabe leer (ver
docstring de `parser_factura_distribuidora.py`): el layout tabular real de EDELAP es más
entreverado y no está cubierto por este test — es trabajo pendiente documentado en el spec.
Los valores usados acá son los reales de una factura EDELAP (Media Tensión, tarifa T5M12)
inspeccionada durante la sesión.
"""

import pytest
from reportlab.pdfgen import canvas

from src.domain.telemetria.exceptions import FacturaDistribuidoraIlegibleError
from src.infrastructure.pdfplumber.parser_factura_distribuidora import (
    PdfplumberParserFacturaDistribuidora,
)

PLANTA_ID = "c64fd625-0037-4caa-b68a-800e8e0ee548"

LINEAS_FACTURA_COMPLETA = [
    "Distribuidora: EMPRESA DISTRIBUIDORA LA PLATA S.A.",
    "Nº de Factura: 0020-01988580",
    "Período: 2026-11",
    "Tarifa: T5M12",
    "Días facturados: 30",
    "Energía activa punta: 68310 kWh",
    "Energía activa resto: 187506 kWh",
    "Energía activa valle: 59994 kWh",
    "Potencia contratada punta: 800.000 kW",
    "Potencia contratada fuera punta: 850.000 kW",
    "Potencia adquirida punta: 1049.000 kW",
    "Potencia adquirida fuera punta: 1082.000 kW",
    "Importe potencia: $ 7.664.856,62",
    "Importe energía: $ 638.572,35",
    "Importe total: $ 21.031.736,78",
]


def _generar_pdf(ruta: str, lineas: list[str]) -> None:
    c = canvas.Canvas(ruta)
    y = 800
    for linea in lineas:
        c.drawString(50, y, linea)
        y -= 20
    c.save()


def test_parsear_factura_completa_extrae_campos_reales(tmp_path):
    ruta_pdf = str(tmp_path / "factura.pdf")
    _generar_pdf(ruta_pdf, LINEAS_FACTURA_COMPLETA)

    factura = PdfplumberParserFacturaDistribuidora().parsear(ruta_pdf, PLANTA_ID)

    assert factura.planta_id == PLANTA_ID
    assert factura.periodo == "2026-11"
    assert factura.proveedor == "EDELAP"
    assert factura.tipo_dato == "potencia"
    assert factura.numero_factura == "0020-01988580"
    assert factura.tarifa == "T5M12"
    assert factura.dias_facturados == 30
    # El parser de EdeLAP solo produce potencia (tipo_dato="potencia"): la energía la
    # factura CAMMESA en un documento aparte, sin parser todavía (ver spec, Tarea 2).
    assert factura.energia_activa_punta_kwh is None
    assert factura.energia_facturada_kwh is None
    assert factura.potencia_contratada_punta_kw == pytest.approx(800.0)
    assert factura.potencia_contratada_fuera_punta_kw == pytest.approx(850.0)
    assert factura.potencia_adquirida_punta_kw == pytest.approx(1049.0)
    assert factura.potencia_adquirida_fuera_punta_kw == pytest.approx(1082.0)
    assert factura.potencia_excedida_punta_kw == pytest.approx(249.0)
    assert factura.potencia_excedida_fuera_punta_kw == pytest.approx(232.0)
    assert factura.importe_potencia_ars == pytest.approx(7664856.62)
    assert factura.importe_energia_ars is None
    assert factura.importe_total_ars == pytest.approx(21031736.78)
    assert factura.fuente_archivo == "factura.pdf"


def test_parsear_factura_sin_campos_obligatorios_lanza_ilegible(tmp_path):
    ruta_pdf = str(tmp_path / "factura_incompleta.pdf")
    _generar_pdf(ruta_pdf, ["Distribuidora: EDELAP", "Tarifa: T5M12"])

    with pytest.raises(FacturaDistribuidoraIlegibleError):
        PdfplumberParserFacturaDistribuidora().parsear(ruta_pdf, PLANTA_ID)


def test_parsear_pdf_inexistente_lanza_ilegible(tmp_path):
    with pytest.raises(FacturaDistribuidoraIlegibleError):
        PdfplumberParserFacturaDistribuidora().parsear(str(tmp_path / "no_existe.pdf"), PLANTA_ID)

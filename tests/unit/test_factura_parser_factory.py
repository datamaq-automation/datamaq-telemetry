"""tests/unit/test_factura_parser_factory.py — Tests para FacturaParserFactory."""

from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from src.domain.telemetria.exceptions import FacturaDistribuidoraIlegibleError
from src.infrastructure.pdfplumber.factura_parser_factory import FacturaParserFactory
from src.infrastructure.pdfplumber.parser_factura_distribuidora import (
    ParserFacturaEnergiaCammesa,
    ParserFacturaPotenciaEdelap,
)


def _crear_pdf_simple(ruta: Path, texto: str) -> str:
    c = canvas.Canvas(str(ruta), pagesize=(600, 800))
    c.setFont("Helvetica", 10)
    c.drawString(50, 750, texto)
    c.save()
    return str(ruta)


class TestFacturaParserFactory:
    def test_crear_por_tipo_validos(self):
        assert isinstance(FacturaParserFactory.crear_por_tipo("potencia"), ParserFacturaPotenciaEdelap)
        assert isinstance(FacturaParserFactory.crear_por_tipo("edelap"), ParserFacturaPotenciaEdelap)
        assert isinstance(FacturaParserFactory.crear_por_tipo("energia"), ParserFacturaEnergiaCammesa)
        assert isinstance(FacturaParserFactory.crear_por_tipo("cammesa"), ParserFacturaEnergiaCammesa)

    def test_crear_por_tipo_invalido_lanza_value_error(self):
        with pytest.raises(ValueError, match="Tipo de parser 'desconocido' no reconocido"):
            FacturaParserFactory.crear_por_tipo("desconocido")

    def test_detectar_y_crear_edelap(self, tmp_path: Path):
        pdf_path = tmp_path / "factura_edelap.pdf"
        _crear_pdf_simple(pdf_path, "EMPRESA DISTRIBUIDORA LA PLATA S.A. - LIQUIDACION SERVICIO")

        parser = FacturaParserFactory.detectar_y_crear(pdf_path)
        assert isinstance(parser, ParserFacturaPotenciaEdelap)

    def test_detectar_y_crear_cammesa(self, tmp_path: Path):
        pdf_path = tmp_path / "factura_cammesa.pdf"
        _crear_pdf_simple(pdf_path, "CAMMESA - MERCADO ELECTRICO MAYORISTA - FACTURA")

        parser = FacturaParserFactory.detectar_y_crear(pdf_path)
        assert isinstance(parser, ParserFacturaEnergiaCammesa)

    def test_detectar_y_crear_desconocido_lanza_error(self, tmp_path: Path):
        pdf_path = tmp_path / "factura_random.pdf"
        _crear_pdf_simple(pdf_path, "COMPROBANTE COMERCIAL GENERICO SIN DISTRIBUIDORA")

        with pytest.raises(FacturaDistribuidoraIlegibleError, match="No se pudo determinar"):
            FacturaParserFactory.detectar_y_crear(pdf_path)

    def test_detectar_y_crear_archivo_inexistente(self, tmp_path: Path):
        with pytest.raises(FacturaDistribuidoraIlegibleError, match="El archivo no existe"):
            FacturaParserFactory.detectar_y_crear(tmp_path / "no_existe.pdf")

"""src/infrastructure/pdfplumber/factura_parser_factory.py.

Factory Method con auto-detección para parsers de facturas de distribuidoras eléctricas.
Permite instanciar el parser correspondiente por clave explícita o analizando el
contenido del documento PDF.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pdfplumber

from src.domain.sge.ports import ParserFacturaDistribuidoraPort
from src.domain.telemetria.exceptions import FacturaDistribuidoraIlegibleError
from src.infrastructure.pdfplumber.parser_factura_distribuidora import (
    ParserFacturaEnergiaCammesa,
    ParserFacturaPotenciaEdelap,
)


class FacturaParserFactory:
    """Fábrica de parsers de facturas de distribuidora con soporte de auto-detección."""

    _REGISTRO: ClassVar[dict[str, type[ParserFacturaDistribuidoraPort]]] = {
        "potencia": ParserFacturaPotenciaEdelap,
        "edelap": ParserFacturaPotenciaEdelap,
        "energia": ParserFacturaEnergiaCammesa,
        "cammesa": ParserFacturaEnergiaCammesa,
    }

    @classmethod
    def crear_por_tipo(cls, tipo: str) -> ParserFacturaDistribuidoraPort:
        """Instancia un parser a partir de su identificador o tipo de dato."""
        tipo_normalizado = tipo.strip().lower()
        parser_cls = cls._REGISTRO.get(tipo_normalizado)
        if not parser_cls:
            disponibles = ", ".join(sorted(cls._REGISTRO.keys()))
            raise ValueError(f"Tipo de parser '{tipo}' no reconocido. Disponibles: {disponibles}")
        return parser_cls()

    @classmethod
    def detectar_y_crear(cls, ruta_pdf: str | Path) -> ParserFacturaDistribuidoraPort:
        """Analiza las primeras páginas del PDF y resuelve el parser adecuado según firmas de texto."""
        ruta = Path(ruta_pdf)
        if not ruta.is_file():
            raise FacturaDistribuidoraIlegibleError(f"El archivo no existe: {ruta}")

        try:
            with pdfplumber.open(ruta) as pdf:
                if not pdf.pages:
                    raise FacturaDistribuidoraIlegibleError(f"El archivo PDF está vacío: {ruta}")

                texto_paginas = []
                for p in pdf.pages[:2]:
                    t = p.extract_text()
                    if t:
                        texto_paginas.append(t.upper())
                texto_completo = "\n".join(texto_paginas)
        except Exception as e:
            if isinstance(e, FacturaDistribuidoraIlegibleError):
                raise
            raise FacturaDistribuidoraIlegibleError(f"Error al abrir o leer el PDF: {e}") from e

        if "CAMMESA" in texto_completo or "MERCADO ELECTRICO MAYORISTA" in texto_completo:
            return ParserFacturaEnergiaCammesa()

        if "EDELAP" in texto_completo or "EMPRESA DISTRIBUIDORA LA PLATA" in texto_completo:
            return ParserFacturaPotenciaEdelap()

        raise FacturaDistribuidoraIlegibleError(
            f"No se pudo determinar la distribuidora emisora de la factura en {ruta.name}. "
            "Especifique el tipo manualmente con --tipo (potencia/energia)."
        )

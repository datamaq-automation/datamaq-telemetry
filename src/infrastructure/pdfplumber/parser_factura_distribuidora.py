"""src/infrastructure/pdfplumber/parser_factura_distribuidora.py.

Implementación de ParserFacturaDistribuidoraPort con la librería `pdfplumber` (pure-Python,
sin binarios de sistema). Ver `specs/factura-distribuidora.md` §2.1 para la justificación de
la elección y sus límites conocidos.

Nota de campo (sesión 2026-09-24): se inspeccionó una factura real de EDELAP (Media Tensión,
tarifa T5M12) extraída con `pdfplumber.page.extract_text()`. El layout tabular de esa factura
llega muy entreverado (columnas de distintas filas quedan pegadas en el texto plano), así que
las expresiones regulares de este módulo están ancladas a etiquetas de campo en un layout
"etiqueta: valor" simple, no al layout real de EDELAP. Extraer con confianza desde el PDF real
de producción va a requerir revisar `page.extract_words()` (coordenadas x/y) o
`page.extract_tables()` en vez de `extract_text()` — quedó documentado como trabajo pendiente
para cuando se cargue la primera factura real, no bloqueante para esta iteración.
"""

import re

import pdfplumber

from src.domain.sge.entities import FacturaDistribuidora
from src.domain.sge.ports import ParserFacturaDistribuidoraPort
from src.domain.telemetria.exceptions import FacturaDistribuidoraIlegibleError

_DISTRIBUIDORAS_CONOCIDAS = {
    "EMPRESA DISTRIBUIDORA LA PLATA": "EDELAP",
    "EMPRESA DISTRIBUIDORA Y COMERCIALIZADORA NORTE": "EDENOR",
    "EMPRESA DISTRIBUIDORA SUR": "EDESUR",
}


def _numero_ar(texto: str) -> float:
    """Convierte un importe en $ con formato AR ('21.031.736,78', '.' miles ',' decimal) a float."""
    limpio = texto.strip().replace(".", "").replace(",", ".")
    return float(limpio)


def _numero_kw(texto: str) -> float:
    """Convierte una magnitud de kWh/kW/días: la factura las trae con '.' decimal simple
    ('800.000' = 800.0 kW), no con el formato AR de miles que sí usan los importes en $."""
    return float(texto.strip())


def _buscar(patron: str, texto: str, flags: int = re.IGNORECASE) -> str | None:
    m = re.search(patron, texto, flags)
    return m.group(1).strip() if m else None


def _buscar_numero(patron: str, texto: str) -> float | None:
    """Para importes en $ (formato AR)."""
    valor = _buscar(patron, texto)
    return _numero_ar(valor) if valor is not None else None


def _buscar_numero_kw(patron: str, texto: str) -> float | None:
    """Para magnitudes de kWh/kW (decimal simple, sin separador de miles)."""
    valor = _buscar(patron, texto)
    return _numero_kw(valor) if valor is not None else None


def _normalizar_distribuidora(nombre: str) -> str:
    nombre_norm = nombre.strip().upper()
    for clave, sigla in _DISTRIBUIDORAS_CONOCIDAS.items():
        if clave in nombre_norm:
            return sigla
    return nombre.strip()


class PdfplumberParserFacturaDistribuidora(ParserFacturaDistribuidoraPort):
    """Extrae los campos de POTENCIA de una factura de distribuidora en PDF con texto seleccionable.

    Representa el documento de EdeLAP (potencia) del caso real UPP, no el de CAMMESA (energía):
    ver Tarea 2 de `specs/factura-distribuidora.md` §"Pendientes". Por eso siempre produce
    `tipo_dato="potencia"` con los campos de energía en `None` — un parser de energía (CAMMESA)
    es un adaptador nuevo del mismo puerto, todavía sin escribir (no hay muestra real).
    """

    def parsear(self, ruta_pdf: str, planta_id: str) -> FacturaDistribuidora:
        texto = self._extraer_texto(ruta_pdf)

        periodo = _buscar(r"Per[ií]odo:\s*(\d{4}-\d{2})", texto)
        potencia_contratada_punta = _buscar_numero_kw(r"Potencia contratada punta:\s*([\d.,]+)\s*kW", texto)

        if periodo is None or potencia_contratada_punta is None:
            raise FacturaDistribuidoraIlegibleError(
                f"No se pudieron extraer los campos obligatorios (período o potencia contratada) de '{ruta_pdf}'."
            )

        distribuidora_raw = _buscar(r"Distribuidora:\s*([^\n]+)", texto) or ""
        numero_factura = _buscar(r"N[º°o]\s*de\s*Factura:\s*([\d-]+)", texto) or ""
        tarifa = _buscar(r"Tarifa:\s*(\S+)", texto)
        dias_facturados = _buscar(r"D[ií]as facturados:\s*(\d+)", texto)
        potencia_contratada_fp = _buscar_numero_kw(r"Potencia contratada fuera punta:\s*([\d.,]+)\s*kW", texto)
        potencia_adquirida_p = _buscar_numero_kw(r"Potencia adquirida punta:\s*([\d.,]+)\s*kW", texto)
        potencia_adquirida_fp = _buscar_numero_kw(r"Potencia adquirida fuera punta:\s*([\d.,]+)\s*kW", texto)
        importe_potencia = _buscar_numero(r"Importe potencia:\s*\$?\s*([\d.,]+)", texto)
        importe_total = _buscar_numero(r"Importe total:\s*\$?\s*([\d.,]+)", texto)

        return FacturaDistribuidora(
            id=f"{planta_id}-{periodo}-potencia",
            planta_id=planta_id,
            periodo=periodo,
            proveedor=_normalizar_distribuidora(distribuidora_raw),
            tipo_dato="potencia",
            numero_factura=numero_factura,
            importe_total_ars=importe_total or 0.0,
            tarifa=tarifa,
            dias_facturados=int(dias_facturados) if dias_facturados else None,
            potencia_contratada_punta_kw=potencia_contratada_punta,
            potencia_contratada_fuera_punta_kw=potencia_contratada_fp or 0.0,
            potencia_adquirida_punta_kw=potencia_adquirida_p or potencia_contratada_punta,
            potencia_adquirida_fuera_punta_kw=potencia_adquirida_fp or (potencia_contratada_fp or 0.0),
            importe_potencia_ars=importe_potencia or 0.0,
            fuente_archivo=ruta_pdf.rsplit("/", 1)[-1],
        )

    @staticmethod
    def _extraer_texto(ruta_pdf: str) -> str:
        try:
            with pdfplumber.open(ruta_pdf) as pdf:
                paginas = [pagina.extract_text() or "" for pagina in pdf.pages]
        except Exception as e:
            raise FacturaDistribuidoraIlegibleError(f"No se pudo abrir o leer el PDF '{ruta_pdf}': {e}") from e
        return "\n".join(paginas)

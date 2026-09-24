"""src/infrastructure/pdfplumber/parser_factura_distribuidora.py.

Implementaciones de ParserFacturaDistribuidoraPort con la librería `pdfplumber` (pure-Python,
sin binarios de sistema). Ver `specs/factura-distribuidora.md` §2.1/§2.2 para la justificación
de la elección y el detalle del caso real (UPP: potencia de EdeLAP, energía de CAMMESA).

Nota de diseño (sesión 2026-09-24, segunda pasada): se verificaron 3 facturas reales —dos de
EdeLAP (períodos 2023-12 y 2024-11, mismo cliente) y una de CAMMESA (período 2024-01)— leyendo
su `page.extract_text()`. El layout tabular de ambos proveedores llega entreverado en texto
plano (columnas de filas distintas quedan pegadas), pero las ETIQUETAS que ancla cada campo
son estables entre facturas del mismo proveedor (confirmado comparando las dos de EdeLAP: mismo
orden de secciones, mismos textos fijos). Por eso cada parser de abajo usa regex ancladas a esas
etiquetas sobre el texto plano, no heurísticas de posición (`extract_words()`): con evidencia de
solo un ejemplar de CAMMESA y dos de EdeLAP no hay manera de distinguir con confianza qué parte
de un layout de coordenadas sería estable entre facturas sin ver más muestras, así que una
heurística de posición hoy sería tan frágil como esta y más difícil de auditar a mano. Si una
factura futura rompe alguna de estas regex, el error es legible (`FacturaDistribuidoraIlegibleError`
con el campo que faltó), no un fallo silencioso.
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
    """Convierte un importe en $ con formato AR ('21.031.736,78', '.' miles ',' decimal) a float.

    También sirve para números sin decimales pero con separador de miles ('1.332.048')."""
    limpio = texto.strip().replace(".", "").replace(",", ".")
    return float(limpio)


def _numero_coma(texto: str) -> float:
    """Convierte un número con coma decimal simple, sin separador de miles ('353,610' -> 353.61)."""
    return float(texto.strip().replace(",", "."))


def _numero_kw(texto: str) -> float:
    """Convierte una magnitud de kWh/kW: la factura de EdeLAP las trae con '.' decimal simple
    ('800.000' = 800.0 kW), no con el formato AR de miles que sí usan los importes en $."""
    return float(texto.strip())


def _extraer_texto(ruta_pdf: str) -> str:
    try:
        with pdfplumber.open(ruta_pdf) as pdf:
            paginas = [pagina.extract_text() or "" for pagina in pdf.pages]
    except Exception as e:
        raise FacturaDistribuidoraIlegibleError(f"No se pudo abrir o leer el PDF '{ruta_pdf}': {e}") from e
    return "\n".join(paginas)


def _normalizar_distribuidora(texto: str) -> str:
    texto_norm = texto.upper()
    for clave, sigla in _DISTRIBUIDORAS_CONOCIDAS.items():
        if clave in texto_norm:
            return sigla
    return "DESCONOCIDA"


class ParserFacturaPotenciaEdelap(ParserFacturaDistribuidoraPort):
    """Extrae los campos de POTENCIA de una factura de EdeLAP (tarifa T5M12, Media Tensión).

    Produce siempre `tipo_dato="potencia"` con los campos de energía en `None` — la energía de
    UPP la factura CAMMESA en un documento aparte (`ParserFacturaEnergiaCammesa`).
    """

    def parsear(self, ruta_pdf: str, planta_id: str) -> FacturaDistribuidora:
        texto = _extraer_texto(ruta_pdf)

        periodo_m = re.search(r"Per[ií]odo:\s*\n?\s*(\d{4})(\d{2})\s+N[ºo°]\s*de\s*factura", texto)
        contratadas_m = re.search(r"Transporte Punta:\s*([\d.]+)\s*Transporte Fuera Punta:\s*([\d.]+)", texto)

        if periodo_m is None or contratadas_m is None:
            raise FacturaDistribuidoraIlegibleError(
                f"No se pudieron extraer los campos obligatorios (período o potencia contratada) "
                f"de '{ruta_pdf}' con el parser de EdeLAP."
            )

        periodo = f"{periodo_m.group(1)}-{periodo_m.group(2)}"
        contratada_punta = _numero_kw(contratadas_m.group(1))
        contratada_fp = _numero_kw(contratadas_m.group(2))

        kw_tarifados = re.findall(r"(\d+)kW\s*\*[\d,.]+\s*\$/kW", texto)
        if len(kw_tarifados) < 4:
            raise FacturaDistribuidoraIlegibleError(
                f"No se pudieron extraer los 4 conceptos de potencia tarifados (pico, f.pico y sus "
                f"excesos) de '{ruta_pdf}': se encontraron {len(kw_tarifados)}."
            )
        excedida_punta = float(kw_tarifados[2])
        excedida_fp = float(kw_tarifados[3])

        numero_factura = re.search(r"N[ºo°]\s*de\s*factura:\s*([\d-]+)", texto)
        tarifa = re.search(r"Tipo de tarifa:\s*([A-Z0-9]+)", texto)
        dias = re.search(r"D[ií]as:\s*(\d+)", texto)

        seccion_potencia_m = re.search(r"Potencia Pico por Transporte(.*?)241609298 Potencia punta", texto, re.DOTALL)
        importe_potencia = 0.0
        if seccion_potencia_m:
            importes = re.findall(r"\d[\d.]*,\d{2}", seccion_potencia_m.group(1))
            importe_potencia = sum(_numero_ar(m) for m in importes)

        vencimiento_m = re.search(r"Vencimientos Recargo 1[ºo°]2[ºo°]\s*\n?\d{2}/\d{2}/\d{4}\s+([\d.]+,\d{2})", texto)
        importe_total = _numero_ar(vencimiento_m.group(1)) if vencimiento_m else 0.0

        return FacturaDistribuidora(
            id=f"{planta_id}-{periodo}-potencia",
            planta_id=planta_id,
            periodo=periodo,
            proveedor=_normalizar_distribuidora(texto),
            tipo_dato="potencia",
            numero_factura=numero_factura.group(1) if numero_factura else "",
            importe_total_ars=importe_total,
            tarifa=tarifa.group(1) if tarifa else None,
            dias_facturados=int(dias.group(1)) if dias else None,
            potencia_contratada_punta_kw=contratada_punta,
            potencia_contratada_fuera_punta_kw=contratada_fp,
            potencia_adquirida_punta_kw=contratada_punta + excedida_punta,
            potencia_adquirida_fuera_punta_kw=contratada_fp + excedida_fp,
            importe_potencia_ars=importe_potencia,
            fuente_archivo=ruta_pdf.rsplit("/", 1)[-1],
        )


class ParserFacturaEnergiaCammesa(ParserFacturaDistribuidoraPort):
    """Extrae los campos de ENERGÍA de una factura de CAMMESA (mercado eléctrico mayorista).

    CAMMESA no discrimina la energía por franja horaria (Punta/Resto/Valle) como sí hace EdeLAP:
    factura "Energía Demandada" como un total único del período, que se guarda en
    `energia_activa_total_kwh`. Los cargos de potencia, transporte y adicionales del MEM que
    también trae esta factura no se modelan en esta iteración (ver `specs/factura-distribuidora.md`
    §"Pendientes"): solo se captura el total de energía y el importe total de la factura.
    """

    def parsear(self, ruta_pdf: str, planta_id: str) -> FacturaDistribuidora:
        texto = _extraer_texto(ruta_pdf)

        periodo_m = re.search(r"(\d{2})/(\d{2})/(\d{4})\s*al\s*\d{2}/\d{2}/\d{4}", texto)
        energia_m = re.search(r"SUBTOTAL CARGOS DE POTENCIA\s*\n?\s*(\d+,\d+)", texto)

        if periodo_m is None or energia_m is None:
            raise FacturaDistribuidoraIlegibleError(
                f"No se pudieron extraer los campos obligatorios (período o energía demandada) "
                f"de '{ruta_pdf}' con el parser de CAMMESA."
            )

        periodo = f"{periodo_m.group(3)}-{periodo_m.group(2)}"
        energia_total_kwh = _numero_coma(energia_m.group(1)) * 1000

        numero_factura = re.search(r"\b([A-Z]-\d{4}-\d{8})\b", texto)
        importe_energia_m = re.search(r"SUBTOTAL ENERG[ÍI]A DEMANDADA\s*\n?\s*([\d.]+)", texto)
        importe_total_m = re.search(r"LEY 24065 Art\.70-FNEE \$/MWh\s*\n?\s*([\d.]+,\d{2})", texto)

        return FacturaDistribuidora(
            id=f"{planta_id}-{periodo}-energia",
            planta_id=planta_id,
            periodo=periodo,
            proveedor="CAMMESA",
            tipo_dato="energia",
            numero_factura=numero_factura.group(1) if numero_factura else "",
            importe_total_ars=_numero_ar(importe_total_m.group(1)) if importe_total_m else 0.0,
            energia_activa_total_kwh=energia_total_kwh,
            importe_energia_ars=_numero_ar(importe_energia_m.group(1)) if importe_energia_m else 0.0,
            fuente_archivo=ruta_pdf.rsplit("/", 1)[-1],
        )

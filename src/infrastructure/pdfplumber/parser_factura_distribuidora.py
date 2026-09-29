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
from dataclasses import dataclass

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


# Fila de lectura de energía del bloque "Lecturas": medidor · concepto · lectura anterior · actual ·
# constante · consumo · marca. `extract_text()` pega a continuación la columna de cargos de OTRO
# renglón (la fila de reactiva punta trae el cargo de valle), así que se lee solo hasta la marca.
_RE_FILA_ENERGIA = re.compile(
    r"^\d+ Energia (activa|reactiva) (punta|resto|valle) \d+ \d+ [\d.]+ (\d+) (\S+)(?: |$)", re.IGNORECASE
)
_RE_TOTAL_ENERGIA = re.compile(r"Total de energ[ií]a activa:\s*(\d+)\s*KWh")
_FRANJAS = ("punta", "resto", "valle")


@dataclass(frozen=True)
class _EnergiaRegistrada:
    punta_kwh: float | None = None
    resto_kwh: float | None = None
    valle_kwh: float | None = None
    total_kwh: float | None = None
    reactiva_punta_kvarh: float | None = None
    reactiva_resto_kvarh: float | None = None
    reactiva_valle_kvarh: float | None = None


def _energia_registrada(texto: str, ruta_pdf: str) -> _EnergiaRegistrada:
    """Energía activa y reactiva registradas por el medidor de la distribuidora, por franja.

    No es energía facturada (decisión 2026-09-28, D1): la vende CAMMESA. Las filas repetidas (cambio
    de medidor, 2024-02, una con consumo 0) se suman, porque la energía se acumula. La activa se
    cruza contra el "Total de energía activa" impreso (D6). Cualquier fila que no se entienda es un
    error: no se adivina. Sin filas ni total, la factura no informa el dato y todo queda en None.
    """
    suma: dict[tuple[str, str], float] = {}
    for linea in texto.splitlines():
        if not re.match(r"^\d+ Energia ", linea):
            continue
        fila = _RE_FILA_ENERGIA.match(linea)
        if fila is None:
            raise FacturaDistribuidoraIlegibleError(f"Fila de lectura de energía ilegible en '{ruta_pdf}': '{linea}'")
        tipo, franja, consumo, marca = fila.group(1).lower(), fila.group(2).lower(), fila.group(3), fila.group(4)
        if marca != "R":
            raise FacturaDistribuidoraIlegibleError(
                f"Marca de lectura '{marca}' (se esperaba 'R', lectura real) en '{ruta_pdf}': '{linea}'"
            )
        suma[(tipo, franja)] = suma.get((tipo, franja), 0.0) + float(consumo)

    totales = {float(t) for t in _RE_TOTAL_ENERGIA.findall(texto)}
    if not suma and not totales:
        return _EnergiaRegistrada()
    if len(totales) != 1:
        raise FacturaDistribuidoraIlegibleError(
            f"'{ruta_pdf}' no trae un único 'Total de energía activa' para cruzar la energía registrada: {sorted(totales)}."
        )
    total = totales.pop()
    for tipo in ("activa", "reactiva"):
        faltan = [f for f in _FRANJAS if (tipo, f) not in suma]
        if faltan and (tipo == "activa" or len(faltan) < len(_FRANJAS)):
            raise FacturaDistribuidoraIlegibleError(
                f"Faltan filas de energía {tipo} ({', '.join(faltan)}) del bloque Lecturas en '{ruta_pdf}'."
            )
    punta, resto, valle = (suma[("activa", f)] for f in _FRANJAS)
    if punta + resto + valle != total:
        raise FacturaDistribuidoraIlegibleError(
            f"En '{ruta_pdf}' punta + resto + valle = {punta + resto + valle:.0f} kWh no coincide con el "
            f"'Total de energía activa' impreso ({total:.0f} kWh)."
        )
    return _EnergiaRegistrada(
        punta_kwh=punta,
        resto_kwh=resto,
        valle_kwh=valle,
        total_kwh=total,
        reactiva_punta_kvarh=suma.get(("reactiva", "punta")),
        reactiva_resto_kvarh=suma.get(("reactiva", "resto")),
        reactiva_valle_kvarh=suma.get(("reactiva", "valle")),
    )


class ParserFacturaPotenciaEdelap(ParserFacturaDistribuidoraPort):
    """Extrae los campos de POTENCIA de una factura de EdeLAP (tarifa T5M12, Media Tensión).

    Produce siempre `tipo_dato="potencia"`: la potencia y, si la factura la informa, la energía
    registrada por el medidor (`energia_registrada_*`, `energia_reactiva_*`). Nunca energía
    facturada (`energia_activa_*` en `None`): la de UPP la factura CAMMESA en un documento aparte
    (`ParserFacturaEnergiaCammesa`). Decisión 2026-09-28, D1 a D3.
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

        # Demanda registrada por el medidor ("241609298 Potencia punta 605 583 1.800 1049 R"): es la
        # medición, no un derivado de contratada + exceso (que pondría la contratada en un mes sin
        # exceso, ej. 2024-02 con 508 kW). Un cambio de medidor duplica la línea con 0, por eso el
        # máximo. Fuera de punta = máx(resto, valle), verificado contra las 11 facturas con exceso.
        registrada: dict[str, float] = {}
        for franja, valor in re.findall(r"Potencia (punta|resto|valle) \d+ \d+ [\d.]+ (\d+) R", texto):
            registrada[franja] = max(registrada.get(franja, 0.0), float(valor))
        if "punta" not in registrada or not {"resto", "valle"} & registrada.keys():
            raise FacturaDistribuidoraIlegibleError(
                f"No se pudo extraer la demanda de potencia registrada (punta, resto, valle) de '{ruta_pdf}'."
            )
        adquirida_punta = registrada["punta"]
        adquirida_fp = max(registrada.get("resto", 0.0), registrada.get("valle", 0.0))

        numero_factura = re.search(r"N[ºo°]\s*de\s*factura:\s*([\d-]+)", texto)
        tarifa = re.search(r"Tipo de tarifa:\s*([A-Z0-9]+)", texto)
        dias = re.search(r"D[ií]as:\s*(\d+)", texto)

        # Suma solo las líneas de potencia contratada y exceso (los excesos faltan en un mes sin
        # exceso), no un tramo de texto: en ese tramo también caen intereses por mora y el CTT.
        importes_potencia = re.findall(
            r"(?:Potencia (?:Fuera de )?Pico por Transporte|Exceso de Potencia (?:en|Fuera de) Pico Transporte)"
            r"\s*\d+kW\s*\*[\d.,]+\s*\$/kW\s*([\d.]+,\d{2})",
            texto,
        )
        importe_potencia = sum(_numero_ar(m) for m in importes_potencia)

        # El PDF real trae "Vencimientos Recargo\n1º 10/12/2024 21.031.736,78" (verificado con las
        # 11 facturas de UPP 2023-12..2024-11); se tolera también el "1º2º" pegado en la cabecera.
        vencimiento_m = re.search(
            r"Vencimientos Recargo\s*1[ºo°]\s*(?:2[ºo°]\s*)?\d{2}/\d{2}/\d{4}\s+([\d.]+,\d{2})", texto
        )
        importe_total = _numero_ar(vencimiento_m.group(1)) if vencimiento_m else 0.0
        energia = _energia_registrada(texto, ruta_pdf)

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
            potencia_adquirida_punta_kw=adquirida_punta,
            potencia_adquirida_fuera_punta_kw=adquirida_fp,
            importe_potencia_ars=importe_potencia,
            energia_registrada_punta_kwh=energia.punta_kwh,
            energia_registrada_resto_kwh=energia.resto_kwh,
            energia_registrada_valle_kwh=energia.valle_kwh,
            energia_registrada_total_kwh=energia.total_kwh,
            energia_reactiva_punta_kvarh=energia.reactiva_punta_kvarh,
            energia_reactiva_resto_kvarh=energia.reactiva_resto_kvarh,
            energia_reactiva_valle_kvarh=energia.reactiva_valle_kvarh,
            fuente_archivo=ruta_pdf.rsplit("/", 1)[-1],
        )


_RE_MONEDA_AR = re.compile(r"^[\d.]+(?:,\d{1,2})?$")
_RE_CANTIDAD_MWH = re.compile(r"^\d+,\d{3}$")
_RE_NUMERO_FACTURA_CAMMESA = re.compile(r"^\d{4}-\d{8}$")


class ParserFacturaEnergiaCammesa(ParserFacturaDistribuidoraPort):
    """Extrae los campos de ENERGÍA de una factura de CAMMESA (mercado eléctrico mayorista).

    CAMMESA no discrimina la energía por franja horaria (Punta/Resto/Valle) como sí hace EdeLAP:
    factura "Energía Demandada" como un total único del período, que se guarda en
    `energia_activa_total_kwh`. Los cargos de potencia, transporte y adicionales del MEM que
    también trae esta factura no se modelan en esta iteración (ver `specs/factura-distribuidora.md`
    §"Pendientes"): solo se captura el total de energía y el importe total de la factura.

    Nota de diseño (sesión 2026-09-24, tercera pasada): a diferencia de EdeLAP, acá SÍ hace falta
    `page.extract_words()` (coordenadas) en vez de `extract_text()` lineal. Se detectó con una
    segunda factura real de CAMMESA (cliente distinto, EITAR) que el texto plano pega sin
    separador el valor de "Energía Demandada" a un código de barras/referencia adyacente
    ("0006849353,610 MWh"), de forma no reproducible con regex sobre texto lineal porque no hay
    ningún separador entre ambos tokens. Verificado con las dos facturas reales (UPP y EITAR,
    clientes y períodos distintos): con `extract_words()` el valor de energía es SIEMPRE una
    palabra propia, separada del código, en la misma posición relativa de la tabla
    (columna "Cantidad", fila "Energía Demandada"; ver `specs/factura-distribuidora.md`).
    """

    def parsear(self, ruta_pdf: str, planta_id: str) -> FacturaDistribuidora:
        try:
            with pdfplumber.open(ruta_pdf) as pdf:
                palabras = pdf.pages[0].extract_words()
        except Exception as e:
            raise FacturaDistribuidoraIlegibleError(f"No se pudo abrir o leer el PDF '{ruta_pdf}': {e}") from e

        def _fila(top: float, tolerancia: float = 1.5) -> list[dict]:
            return sorted((p for p in palabras if abs(p["top"] - top) <= tolerancia), key=lambda p: p["x0"])

        periodo_label = next((p for p in palabras if p["text"] == "Periodo"), None)
        energia_label = next((p for p in palabras if p["text"] == "Demandada"), None)
        subtotal_energia_label = next(
            (p for p in palabras if p["text"] == "DEMANDADA" and any(q["text"] == "SUBTOTAL" for q in _fila(p["top"]))),
            None,
        )
        total_label = next((p for p in palabras if p["text"] == "TOTAL"), None)

        if periodo_label is None or energia_label is None or subtotal_energia_label is None:
            raise FacturaDistribuidoraIlegibleError(
                f"No se pudieron ubicar las etiquetas obligatorias (Periodo, Energía Demandada) "
                f"de '{ruta_pdf}' con el parser de CAMMESA."
            )

        fechas = [p for p in _fila(periodo_label["top"]) if re.fullmatch(r"\d{2}/\d{2}/\d{4}", p["text"])]
        cantidad_energia = next((p for p in _fila(energia_label["top"]) if _RE_CANTIDAD_MWH.match(p["text"])), None)
        importe_energia = next(
            (p for p in reversed(_fila(subtotal_energia_label["top"])) if _RE_MONEDA_AR.match(p["text"])), None
        )
        numero_factura = next((p for p in palabras if _RE_NUMERO_FACTURA_CAMMESA.match(p["text"])), None)

        if fechas is None or len(fechas) < 2 or cantidad_energia is None or importe_energia is None:
            raise FacturaDistribuidoraIlegibleError(
                f"No se pudieron extraer los valores obligatorios (período o energía demandada) "
                f"de '{ruta_pdf}' con el parser de CAMMESA."
            )

        _, mes, anio = fechas[-1]["text"].split("/")
        periodo = f"{anio}-{mes}"
        energia_total_kwh = _numero_coma(cantidad_energia["text"]) * 1000

        importe_total = 0.0
        if total_label is not None:
            candidatos = [
                p
                for p in palabras
                if p["top"] >= total_label["top"] - 1
                and p["top"] <= total_label["top"] + 3
                and _RE_MONEDA_AR.match(p["text"])
            ]
            if candidatos:
                importe_total = _numero_ar(max(candidatos, key=lambda p: p["x0"])["text"])

        return FacturaDistribuidora(
            id=f"{planta_id}-{periodo}-energia",
            planta_id=planta_id,
            periodo=periodo,
            proveedor="CAMMESA",
            tipo_dato="energia",
            numero_factura=numero_factura["text"] if numero_factura else "",
            importe_total_ars=importe_total,
            energia_activa_total_kwh=energia_total_kwh,
            importe_energia_ars=_numero_ar(importe_energia["text"]),
            fuente_archivo=ruta_pdf.rsplit("/", 1)[-1],
        )

"""tests/unit/test_parser_factura_distribuidora.py — Parsers reales de facturas PDF con pdfplumber.

Los fixtures de EdeLAP son la salida literal de `pdfplumber.page.extract_text()` sobre las
facturas reales de UPP de los períodos 2023-12 y 2024-11 (mismo cliente y contrato), copiada
sin retoques. Corrección 2026-09-28: la versión anterior era una reconstrucción a mano con un
orden de líneas que el PDF real no tiene. Con ella, el test aceptaba una regex de vencimiento
que fallaba contra los PDFs reales (`importe_total_ars` salía 0.0) y un `importe_potencia_ars`
que sumaba un cargo variable de energía en lugar del exceso fuera de pico. Los fixtures de
CAMMESA (período 2024-01) siguen siendo parciales, por coordenadas (ver su comentario). Los
valores esperados de cada `assert` están verificados a mano contra el PDF original.
"""

import pytest
from reportlab.pdfgen import canvas

from src.domain.telemetria.exceptions import FacturaDistribuidoraIlegibleError
from src.infrastructure.pdfplumber.parser_factura_distribuidora import (
    ParserFacturaEnergiaCammesa,
    ParserFacturaPotenciaEdelap,
)

PLANTA_ID = "c64fd625-0037-4caa-b68a-800e8e0ee548"

# EdeLAP, UPP, período 202411 (noviembre 2024).
LINEAS_EDELAP_202411 = """FRANQUEO A PAGAR
LIQUIDACION DE SERVICIOS PUBLICOS CLASE A TRANSLYF SA
R.N.P.S.P. Nro. 180
202411 0020-01988580
Período Nº de Factura
EMPRESA DISTRIBUIDORA LA PLATA S.A.
COOP UNION PAPELERA PLATENSE LIMITADA
Diagonal 80 Nro 1001 I.V.A.: Responsable Inscripto
Titular del Suministro
Ing. Brutos: Exento Ag.Percepcion: 000-650839-6
514 s/n Cno Centenario 1901 RINGUELET
Remite Sucursal: CITY BELL
Domicilio Postal
14 364 1896 CITY BELL - Tel.: 4722923
CAMINO CENTENARIO s/n . Esq 515 Fondo a 12 / Union Papelera Platense
Ringu GONNET
NIR 0 3512065 01 01/12/2024 Domicilio del suministro
Condición Fiscal: Resp. inscripto CUIT:30707619089 Cond. Ing Br.: Contr. Exento
Indique el número resaltado del renglón superior al momento de
efectuar un reclamo ante nuestras oficinas comerciales
Nº CESP: 35489005515808 Vto.: 07/12/2024 CIIU: 210102
Tipo de tarifa:T5M12 - Media Tension Fecha de emisión: 02/12/2024 Fecha lect. ant.: 01/11/2024 Fecha lect. actual: 01/12/2024 Días: 30
Potencias Contratadas (KW): Punta: Fuera Punta: Transporte Punta: 800.000 Transporte Fuera Punta: 850.000
Consumos de energía (KWh): Excesos de potencias Pond. de cuadros tarif. por unidad:
202405 202406 202407 202408 202409 202410 202411 Punta F. de punta Potencia
Punta: 67230 65790 58626 83394 70002 64854 68310 Valor 0 0 Fecha Días Punta F. Punta
Resto: 168102 171216 135900 198108 154206 159066 187506 Fecha Exceso: 29991231 29991231 1 - 29 6427,2949 5089,3574
Valle: 76032 68148 64278 102222 76284 77040 59994 Fecha de recontratación: 29991231 29991231 2 3 - - 1 0 6801 0 , , 0 0 9 0 4 0 2 0 5394 0 , , 7 0 1 0 8 0 8 0
Total: 311364 305154 258804 383724 300492 300960 315810 30 6439,7549 5099,5361
Consumos de Potencia (KW):
Subsidio al Csmo Energía sin Sub.
Periodos
Descripción de Códigos: Fecha Días Punta Resto Valle Punta Resto Valle
202405 202406 202407 202408 202409 202410 202411
R: Consumo real 1 - 29 5,0948 4,9323 4,8391
E: Consumo estimado Punta: 1040 1057 1048 1055 1145 1089 1049 2 - 1 5,1490 4,9864 4,8932
Fuera Punta: 1021 1071 1044 1048 1103 1107 1082 3 - 0 0,0000 0,0000 0,0000
30 5,0966 4,9341 4,8409
Factor de Potencia:
Concepto Punta Valle Resto
Tg. Fi.: 0,432 0,387 0,444
Total de energía activa: 315810KWh
Recargo:
Lecturas
Nº Medidor Concepto: Cte. Consumo Detalle de Facturación Importe:
Anterior: Actual:
241609298 Energia activa punta 128325 132120 18.000 68310 R Cargo Variable Pico Transp. Sin Subsidio 68310 kWh *5.0966$/kWh 348.149,84
241609298 Energia Reactiva Punta 59057 60698 18.000 29538 R Cargo Variable Valle Transp. Sin Subsidio 59994 kWh *4.8409$/kWh 290.422,51
241609298 Energia activa resto 298123 308540 18.000 187506 R Cargo Variable Resto Transp. Sin Subsidio 187506 kWh *4.9341$/kWh 925.171,12
241609298 Energia Reactiva Resto 133858 138486 18.000 83304 R Potencia Pico por Transporte 800kW *6439.755 $/kW 5.151.803,74
Potencia Fuera de Pico por Transporte 850kW *5099.536 $/kW 4.334.605,73
241609298 Energia activa valle 143516 146849 18.000 59994 R
Exceso de Potencia en Pico Transporte 249kW *9658.956 $/kW 2.405.080,17
241609298 Energia Reactiva Valle 66014 67303 18.000 23202 R
Exceso de Potencia Fuera de Pico Transporte 232kW *7649.831 $/kW 1.774.760,73
241609298 Potencia punta 605 583 1.800 1049 R CTT - Art.49 Res MIySP 763/25 189.486,00
241609298 Potencia resto 605 601 1.800 1082 R
241609298 Potencia valle 615 596 1.800 1073 R
Subtotal Por Servicio Eléctrico sin Subsidio 15.419.479,84
SUBTOTAL POR SERVICIO ELECTRICO 15.419.479,84
IVA Responsable Inscripto - Ley Nac 23.349 27.00000% 4.163.259,56
Ley 11.769 Art. 74 0.00100% 154,19
Ley 11.769 Art. 75 6.00000% 925.168,79
Resolucion Gral. 3337/91 DGI 3.00000% 462.584,40
SUBTOTAL IMPUESTOS 5.551.166,94
Tasa de iluminacion municipal - La Plata 61.090,00
SUBTOTAL CARGOS VARIOS EXENTOS 61.090,00
Su gasto diario de electricidad es de $ 507666,47 Vencimientos Recargo
1º 10/12/2024 21.031.736,78
Próximo Vencimiento: 07/01/2025
I.V.A. del recargo: 43756,51 2º 16/12/2024 220.404,79 21.252.141,57
Página nº 1de 1
Remite Sucursal: CITY BELL
14 364 1896 CITY BELL - Tel.: 4722923
Período: 202411 Nº de factura:0020-01988580
Información Complementaria: Tarifa: T5M12 - Media Tension NIR: 0-3512065-01-01/12/2024
Esta factura incluye Subsidio Estado Nacional por $108151.09 Vencimientos Recargo Importe:
1º 10/12/2024 21.031.736,78
2º 16/12/2024 220.404,79 21.252.141,57
No debe abonarse en banco.""".splitlines()

# EdeLAP, UPP, período 202312 (diciembre 2023) — mismo cliente/contrato, para validar estabilidad.
LINEAS_EDELAP_202312 = """FRANQUEO A PAGAR
LIQUIDACION DE SERVICIOS PUBLICOS CLASE A TRANSLYF SA
R.N.P.S.P. Nro. 180
202312 0020-01719216
Período Nº de Factura
EMPRESA DISTRIBUIDORA LA PLATA S.A.
COOP UNION PAPELERA PLATENSE LIMITADA
Diagonal 80 Nro 1001 I.V.A.: Responsable Inscripto
Titular del Suministro
Ing. Brutos: Exento Ag.Percepcion: 000-650839-6
514 s/n Cno Centenario 1901 RINGUELET
Remite Sucursal: CITY BELL
Domicilio Postal
14 364 1896 CITY BELL - Tel.: 4722923
CAMINO CENTENARIO s/n . Esq 515 Fondo a 12 / Union Papelera Platense
Ringu GONNET
NIR 0 3512065 01 01/01/2024 Domicilio del suministro
Condición Fiscal: Resp. inscripto CUIT:30707619089 Cond. Ing Br.: Contr. Exento
Indique el número resaltado del renglón superior al momento de
efectuar un reclamo ante nuestras oficinas comerciales
Nº CESP: 34529005018003 Vto.: 07/01/2024 CIIU: 210102
Tipo de tarifa:T5M12 - Media Tension Fecha de emisión: 02/01/2024 Fecha lect. ant.: 01/12/2023 Fecha lect. actual: 01/01/2024 Días: 31
Potencias Contratadas (KW): Punta: Fuera Punta: Transporte Punta: 800.000 Transporte Fuera Punta: 850.000
Consumos de energía (KWh): Excesos de potencias Pond. de cuadros tarif. por unidad:
202306 202307 202308 202309 202310 202311 202312 Punta F. de punta Potencia
Punta: 84330 96948 91836 77886 87048 72072 76914 Valor 0 0 Fecha Días Punta F. Punta
Resto: 166230 212904 217206 165690 191898 160092 191304 Fecha Exceso: 29991231 29991231 1 - 31 1459,7565 1188,2103
Valle: 92772 109368 103680 89982 94230 85320 90954 Fecha de recontratación: 29991231 29991231 2 3 - - 0 0 0 0 , , 0 0 0 0 0 0 0 0 0 0 , , 0 0 0 0 0 0 0 0
Total: 343332 419220 412722 333558 373176 317484 359172 31 1459,7565 1188,2103
Consumos de Potencia (KW):
Subsidio al Csmo Energía sin Sub.
Periodos
Descripción de Códigos: Fecha Días Punta Resto Valle Punta Resto Valle
202306 202307 202308 202309 202310 202311 202312
R: Consumo real 1 - 31 1,6271 1,6266 1,6262
E: Consumo estimado Punta: 995 1058 1035 1073 1042 1040 1069 2 - 0 0,0000 0,0000 0,0000
Fuera Punta: 995 1075 1053 1044 1055 1057 1062 3 - 0 0,0000 0,0000 0,0000
31 1,6271 1,6266 1,6262
Factor de Potencia:
Concepto Punta Valle Resto
Tg. Fi.: 0,483 0,492 0,481
Total de energía activa: 359172KWh
Recargo:
Lecturas
Nº Medidor Concepto: Cte. Consumo Detalle de Facturación Importe:
Anterior: Actual:
241609298 Energia activa punta 87106 91379 18.000 76914 R Cargo Variable Pico Transp. Sin Subsidio 76914 kWh *1.6271$/kWh 125.143,00
241609298 Energia Reactiva Punta 42488 44552 18.000 37152 R Cargo Variable Valle Transp. Sin Subsidio 90954 kWh *1.6262$/kWh 147.905,03
241609298 Energia activa resto 200137 210765 18.000 191304 R Cargo Variable Resto Transp. Sin Subsidio 191304 kWh *1.6266$/kWh 311.168,77
241609298 Energia Reactiva Resto 94639 99752 18.000 92034 R Potencia Pico por Transporte 800kW *1459.756 $/kW 1.167.805,19
Potencia Fuera de Pico por Transporte 850kW *1188.210 $/kW 1.009.978,80
241609298 Energia activa valle 97454 102507 18.000 90954 R
Exceso de Potencia en Pico Transporte 269kW *2189.635 $/kW 589.011,74
241609298 Energia Reactiva Valle 47494 49979 18.000 44730 R
Exceso de Potencia Fuera de Pico Transporte 212kW *1782.316 $/kW 377.850,89
241609298 Potencia punta 578 594 1.800 1069 R Intereses cheque rechazado 20.102,99
241609298 Potencia resto 587 590 1.800 1062 R Ajuste de Interes por mora 5,84
241609298 Potencia valle 572 578 1.800 1040 R CTT - Art.49 Res MIySP 763/25 71.834,40
Subtotal Por Servicio Eléctrico sin Subsidio 3.820.806,65
SUBTOTAL POR SERVICIO ELECTRICO 3.820.806,65
IVA Responsable Inscripto - Ley Nac 23.349 27.00000% 1.031.617,80
Ley 11.769 Art. 74 0.00100% 38,21
Ley 11.769 Art. 75 6.00000% 229.248,40
Resolucion Gral. 3337/91 DGI 3.00000% 114.624,20
SUBTOTAL IMPUESTOS 1.375.528,61
Tasa de iluminacion municipal - La Plata 12.000,00
SUBTOTAL CARGOS VARIOS EXENTOS 12.000,00
Su gasto diario de electricidad es de $ 120285,92 Vencimientos Recargo
1º 10/01/2024 5.208.335,26
Próximo Vencimiento: 07/02/2024
I.V.A. del recargo: 29799,94 2º 15/01/2024 150.104,51 5.358.439,77
Página nº 1de 1
Remite Sucursal: CITY BELL
14 364 1896 CITY BELL - Tel.: 4722923
Período: 202312 Nº de factura:0020-01719216
Información Complementaria: Tarifa: T5M12 - Media Tension NIR: 0-3512065-01-01/01/2024
Esta factura incluye Subsidio Estado Nacional por $0 Vencimientos Recargo Importe:
1º 10/01/2024 5.208.335,26
2º 15/01/2024 150.104,51 5.358.439,77
No debe abonarse en banco.""".splitlines()

# CAMMESA: coordenadas (texto, x, top) verificadas con `page.extract_words()` contra dos facturas
# reales (UPP período 2024-01 y EITAR período 2024-08, clientes distintos) — no una reconstrucción
# de línea de texto: el parser de CAMMESA necesita palabras separadas por posición, no texto lineal
# (ver docstring de ParserFacturaEnergiaCammesa). `top` es la distancia al borde superior de la
# página, igual que pdfplumber; estos fixtures reproducen solo las etiquetas y valores que el
# parser usa como ancla, en las mismas filas relativas que la factura real, no el documento
# completo (evita commitear datos personales/impositivos reales de un cliente en el repo).
PALABRAS_CAMMESA_UPP_202401 = [
    ("0057-00299314", 430, 67),
    ("Periodo", 100, 197),
    ("01/01/2024", 250, 197),
    ("31/01/2024", 400, 197),
    ("353,610", 50, 285),
    ("MWh", 150, 285),
    ("Energía", 250, 285),
    ("Demandada", 350, 285),
    ("SUBTOTAL", 50, 296),
    ("ENERGÍA", 200, 296),
    ("DEMANDADA", 320, 296),
    ("1.332.048", 480, 296),
    ("TOTAL", 100, 550),
    ("24.627.268,27", 350, 551),
]

# CAMMESA, EITAR (planta distinta, sin medidor de datamaq instalado aún), período 2024-08 — segunda
# muestra real, usada para confirmar que el parser no quedó pegado al cliente/período de la primera.
PALABRAS_CAMMESA_EITAR_202408 = [
    ("0057-00008747", 430, 67),
    ("Periodo", 100, 197),
    ("01/08/2024", 250, 197),
    ("31/08/2024", 400, 197),
    ("41,760", 50, 285),
    ("MWh", 150, 285),
    ("Energía", 250, 285),
    ("Demandada", 350, 285),
    ("SUBTOTAL", 50, 296),
    ("ENERGÍA", 200, 296),
    ("DEMANDADA", 320, 296),
    ("509.455", 480, 296),
    ("TOTAL", 100, 550),
    ("5.972.126,39", 350, 551),
]


def _generar_pdf_por_palabras(ruta: str, palabras: list[tuple[str, float, float]]) -> None:
    """Dibuja cada palabra en su posición (x, top) — reproduce lo que ve `extract_words()` en una
    factura real, a diferencia de `_generar_pdf` (una línea de texto = una línea del PDF)."""
    alto_pagina = 800
    c = canvas.Canvas(ruta, pagesize=(620, alto_pagina))
    c.setFont("Helvetica", 9)
    for texto, x, top in palabras:
        c.drawString(x, alto_pagina - top, texto)
    c.save()


def _generar_pdf(ruta: str, lineas: list[str]) -> None:
    """Una línea del texto real por línea del PDF — reproduce el mismo `extract_text()` jumbled
    que produce la factura real, no un layout limpio inventado."""
    c = canvas.Canvas(ruta, pagesize=(2200, 1600))
    c.setFont("Helvetica", 9)
    y = 1550
    for linea in lineas:
        c.drawString(20, y, linea)
        y -= 13
    c.save()


def test_edelap_factura_202411_extrae_campos_reales(tmp_path):
    ruta_pdf = str(tmp_path / "edelap_202411.pdf")
    _generar_pdf(ruta_pdf, LINEAS_EDELAP_202411)

    factura = ParserFacturaPotenciaEdelap().parsear(ruta_pdf, PLANTA_ID)

    assert factura.planta_id == PLANTA_ID
    assert factura.periodo == "2024-11"
    assert factura.proveedor == "EDELAP"
    assert factura.tipo_dato == "potencia"
    assert factura.numero_factura == "0020-01988580"
    assert factura.tarifa == "T5M12"
    assert factura.dias_facturados == 30
    assert factura.energia_activa_punta_kwh is None
    assert factura.energia_facturada_kwh is None
    assert factura.potencia_contratada_punta_kw == pytest.approx(800.0)
    assert factura.potencia_contratada_fuera_punta_kw == pytest.approx(850.0)
    assert factura.potencia_adquirida_punta_kw == pytest.approx(1049.0)
    assert factura.potencia_adquirida_fuera_punta_kw == pytest.approx(1082.0)
    assert factura.potencia_excedida_punta_kw == pytest.approx(249.0)
    assert factura.potencia_excedida_fuera_punta_kw == pytest.approx(232.0)
    # Pico + Fuera de Pico por Transporte + sus dos excesos; los cargos variables son de energía.
    assert factura.importe_potencia_ars == pytest.approx(5151803.74 + 4334605.73 + 2405080.17 + 1774760.73)
    assert factura.importe_energia_ars is None
    assert factura.importe_total_ars == pytest.approx(21031736.78)
    assert factura.fuente_archivo == "edelap_202411.pdf"


def test_edelap_factura_202312_confirma_layout_estable_entre_periodos(tmp_path):
    """Misma planta, período distinto: el contrato (potencia contratada) no cambia, el consumo sí.
    Sirve como señal de que el parser no está hardcodeado a una sola factura."""
    ruta_pdf = str(tmp_path / "edelap_202312.pdf")
    _generar_pdf(ruta_pdf, LINEAS_EDELAP_202312)

    factura = ParserFacturaPotenciaEdelap().parsear(ruta_pdf, PLANTA_ID)

    assert factura.periodo == "2023-12"
    assert factura.numero_factura == "0020-01719216"
    assert factura.dias_facturados == 31
    # Mismo contrato que la factura de 202411 — confirma que la regex no capturó un dato puntual.
    assert factura.potencia_contratada_punta_kw == pytest.approx(800.0)
    assert factura.potencia_contratada_fuera_punta_kw == pytest.approx(850.0)
    assert factura.potencia_adquirida_punta_kw == pytest.approx(1069.0)
    assert factura.potencia_adquirida_fuera_punta_kw == pytest.approx(1062.0)
    assert factura.potencia_excedida_punta_kw == pytest.approx(269.0)
    assert factura.potencia_excedida_fuera_punta_kw == pytest.approx(212.0)
    assert factura.importe_potencia_ars == pytest.approx(1167805.19 + 1009978.80 + 589011.74 + 377850.89)
    assert factura.importe_total_ars == pytest.approx(5208335.26)


def test_edelap_factura_sin_campos_obligatorios_lanza_ilegible(tmp_path):
    ruta_pdf = str(tmp_path / "edelap_incompleta.pdf")
    _generar_pdf(ruta_pdf, ["Distribuidora: EDELAP", "Tarifa: T5M12"])

    with pytest.raises(FacturaDistribuidoraIlegibleError):
        ParserFacturaPotenciaEdelap().parsear(ruta_pdf, PLANTA_ID)


def test_edelap_pdf_inexistente_lanza_ilegible(tmp_path):
    with pytest.raises(FacturaDistribuidoraIlegibleError):
        ParserFacturaPotenciaEdelap().parsear(str(tmp_path / "no_existe.pdf"), PLANTA_ID)


def test_cammesa_factura_202401_extrae_campos_reales(tmp_path):
    ruta_pdf = str(tmp_path / "cammesa_202401.pdf")
    _generar_pdf_por_palabras(ruta_pdf, PALABRAS_CAMMESA_UPP_202401)

    factura = ParserFacturaEnergiaCammesa().parsear(ruta_pdf, PLANTA_ID)

    assert factura.planta_id == PLANTA_ID
    assert factura.periodo == "2024-01"
    assert factura.proveedor == "CAMMESA"
    assert factura.tipo_dato == "energia"
    assert factura.numero_factura == "0057-00299314"
    assert factura.energia_activa_total_kwh == pytest.approx(353610.0)
    assert factura.energia_facturada_kwh == pytest.approx(353610.0)
    # No discrimina por franja horaria (a diferencia de EdeLAP): quedan en None.
    assert factura.energia_activa_punta_kwh is None
    assert factura.potencia_contratada_punta_kw is None
    assert factura.importe_energia_ars == pytest.approx(1332048.0)
    assert factura.importe_total_ars == pytest.approx(24627268.27)
    assert factura.fuente_archivo == "cammesa_202401.pdf"


def test_cammesa_factura_202408_confirma_layout_estable_entre_clientes(tmp_path):
    """Cliente distinto (EITAR, no UPP) y período distinto: confirma que el parser generaliza
    y no quedó pegado a un solo ejemplar — bug real encontrado y corregido en esta sesión: la
    versión anterior (regex sobre `extract_text()` lineal) fallaba directo contra esta factura."""
    ruta_pdf = str(tmp_path / "cammesa_202408.pdf")
    _generar_pdf_por_palabras(ruta_pdf, PALABRAS_CAMMESA_EITAR_202408)

    factura = ParserFacturaEnergiaCammesa().parsear(ruta_pdf, PLANTA_ID)

    assert factura.periodo == "2024-08"
    assert factura.numero_factura == "0057-00008747"
    assert factura.energia_activa_total_kwh == pytest.approx(41760.0)
    assert factura.importe_energia_ars == pytest.approx(509455.0)
    assert factura.importe_total_ars == pytest.approx(5972126.39)


def test_cammesa_factura_sin_campos_obligatorios_lanza_ilegible(tmp_path):
    ruta_pdf = str(tmp_path / "cammesa_incompleta.pdf")
    _generar_pdf(ruta_pdf, ["CAMMESA", "FACTURA"])

    with pytest.raises(FacturaDistribuidoraIlegibleError):
        ParserFacturaEnergiaCammesa().parsear(ruta_pdf, PLANTA_ID)


def test_cammesa_pdf_inexistente_lanza_ilegible(tmp_path):
    with pytest.raises(FacturaDistribuidoraIlegibleError):
        ParserFacturaEnergiaCammesa().parsear(str(tmp_path / "no_existe.pdf"), PLANTA_ID)

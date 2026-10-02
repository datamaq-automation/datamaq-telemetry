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

# EdeLAP, UPP, período 202402: mes sin exceso de potencia (demanda registrada 508/529 kW, por
# debajo de la contratada), con cambio de medidor (líneas de lectura duplicadas en 0), interés por
# mora y CTT entre las líneas de potencia, y el total solo en la página 2 (la 1 lo trae enmascarado).
LINEAS_EDELAP_202402 = """FRANQUEO A PAGAR
LIQUIDACION DE SERVICIOS PUBLICOS CLASE A TRANSLYF SA
R.N.P.S.P. Nro. 180
202402 0020-01766800
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
NIR 0 3512065 01 01/03/2024 Domicilio del suministro
Condición Fiscal: Resp. inscripto CUIT:30707619089 Cond. Ing Br.: Contr. Exento
Indique el número resaltado del renglón superior al momento de
efectuar un reclamo ante nuestras oficinas comerciales
Nº CESP: 35099005105506 Vto.: 07/03/2024 CIIU: 210102
Tipo de tarifa:T5M12 - Media Tension Fecha de emisión: 01/03/2024 Fecha lect. ant.: 01/02/2024 Fecha lect. actual: 01/03/2024 Días: 29
Potencias Contratadas (KW): Punta: Fuera Punta: Transporte Punta: 800.000 Transporte Fuera Punta: 850.000
Consumos de energía (KWh): Excesos de potencias Pond. de cuadros tarif. por unidad:
202308 202309 202310 202311 202312 202401 202402 Punta F. de punta Potencia
Punta: 91836 77886 87048 72072 76914 80514 47826 Valor 0 0 Fecha Días Punta F. Punta
Resto: 217206 165690 191898 160092 191304 186750 103086 Fecha Exceso: 29991231 29991231 1 - 29 1630,3042 1188,2103
Valle: 103680 89982 94230 85320 90954 86346 51210 Fecha de recontratación: 29991231 29991231 2 3 - - 0 0 0 0 , , 0 0 0 0 0 0 0 0 0 0 , , 0 0 0 0 0 0 0 0
Total: 412722 333558 373176 317484 359172 353610 202122 29 1630,3042 1188,2103
Consumos de Potencia (KW):
Subsidio al Csmo Energía sin Sub.
Periodos
Descripción de Códigos: Fecha Días Punta Resto Valle Punta Resto Valle
202308 202309 202310 202311 202312 202401 202402
R: Consumo real 1 - 29 3,4217 3,3098 3,2457
E: Consumo estimado Punta: 1035 1073 1042 1040 1069 1046 508 2 - 0 0,0000 0,0000 0,0000
Fuera Punta: 1053 1044 1055 1057 1062 1073 529 3 - 0 0,0000 0,0000 0,0000
29 3,4217 3,3098 3,2457
Factor de Potencia:
Concepto Punta Valle Resto
Tg. Fi.: 0,196 0,191 0,195
Total de energía activa: 202122KWh
Recargo:
Lecturas
Nº Medidor Concepto: Cte. Consumo Detalle de Facturación Importe:
Anterior: Actual:
241609298 Energia activa punta 95852 98509 18.000 47826 R Cargo Variable Pico Transp. Sin Subsidio 47826 kWh *3.4217$/kWh 163.644,74
241609298 Energia activa punta 95852 95852 18.000 0 R Cargo Variable Valle Transp. Sin Subsidio 51210 kWh *3.2457$/kWh 166.209,99
241609298 Energia Reactiva Punta 46583 47104 18.000 9378 R Cargo Variable Resto Transp. Sin Subsidio 103086 kWh *3.3098$/kWh 341.197,75
241609298 Energia Reactiva Punta 46583 46583 18.000 0 R Potencia Pico por Transporte 800kW *1630.304 $/kW 1.304.243,38
Potencia Fuera de Pico por Transporte 850kW *1188.210 $/kW 1.009.978,80
241609298 Energia activa resto 221140 226867 18.000 103086 R
Ajuste de Interes por mora 132.493,29
241609298 Energia activa resto 221140 221140 18.000 0 R
CTT - Art.49 Res MIySP 763/25 40.424,40
241609298 Energia Reactiva Resto 104436 105554 18.000 20124 R
241609298 Energia Reactiva Resto 104436 104436 18.000 0 R
241609298 Energia activa valle 107304 110149 18.000 51210 R
241609298 Energia activa valle 107304 107304 18.000 0 R
241609298 Energia Reactiva Valle 52172 52716 18.000 9792 R
241609298 Energia Reactiva Valle 52172 52172 18.000 0 R
241609298 Potencia punta 0 282 1.800 508 R
241609298 Potencia punta 581 0 1.800 0 R
241609298 Potencia resto 0 294 1.800 529 R
241609298 Potencia resto 596 0 1.800 0 R
241609298 Potencia valle 0 287 1.800 517 R
241609298 Potencia valle 587 0 1.800 0 R
Subtotal Por Servicio Eléctrico sin Subsidio 3.158.192,35
SUBTOTAL POR SERVICIO ELECTRICO 3.158.192,35
IVA Responsable Inscripto - Ley Nac 23.349 27.00000% 852.711,93
Ley 11.769 Art. 74 0.00100% 31,58
Ley 11.769 Art. 75 6.00000% 189.491,54
Resolucion Gral. 3337/91 DGI 3.00000% 94.745,77
Su gasto diario de electricidad es de $ 102940,51 Vencimientos Recargo
1º ******** ********
Próximo Vencimiento: ********
I.V.A. del recargo: ******** 2º ******** ******** ********
Página nº 1de 2
Remite Sucursal: CITY BELL
14 364 1896 CITY BELL - Tel.: 4722923
Período: 202402 Nº de factura:0020-01766800
Información Complementaria: Tarifa: T5M12 - Media Tension NIR: 0-3512065-01-01/03/2024
Esta factura incluye Subsidio Estado Nacional por $0 Vencimientos Recargo Importe:
1º ******** ********
2º ******** ******** ********
No debe abonarse en banco.
FRANQUEO A PAGAR
LIQUIDACION DE SERVICIOS PUBLICOS CLASE A TRANSLYF SA
R.N.P.S.P. Nro. 180
202402 0020-01766800
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
NIR 0 3512065 01 01/03/2024 Domicilio del suministro
Condición Fiscal: Resp. inscripto CUIT:30707619089 Cond. Ing Br.: Contr. Exento
Indique el número resaltado del renglón superior al momento de
efectuar un reclamo ante nuestras oficinas comerciales
Nº CESP: 35099005105506 Vto.: 07/03/2024 CIIU: 210102
Tipo de tarifa:T5M12 - Media Tension Fecha de emisión: 01/03/2024 Fecha lect. ant.: 01/02/2024 Fecha lect. actual: 01/03/2024 Días: 29
Potencias Contratadas (KW): Punta: Fuera Punta: Transporte Punta: 800.000 Transporte Fuera Punta: 850.000
Consumos de energía (KWh): Excesos de potencias Pond. de cuadros tarif. por unidad:
202308 202309 202310 202311 202312 202401 202402 Punta F. de punta Potencia
Punta: 91836 77886 87048 72072 76914 80514 47826 Valor 0 0 Fecha Días Punta F. Punta
Resto: 217206 165690 191898 160092 191304 186750 103086 Fecha Exceso: 29991231 29991231 1 - 29 1630,3042 1188,2103
Valle: 103680 89982 94230 85320 90954 86346 51210 Fecha de recontratación: 29991231 29991231 2 3 - - 0 0 0 0 , , 0 0 0 0 0 0 0 0 0 0 , , 0 0 0 0 0 0 0 0
Total: 412722 333558 373176 317484 359172 353610 202122 29 1630,3042 1188,2103
Consumos de Potencia (KW):
Subsidio al Csmo Energía sin Sub.
Periodos
Descripción de Códigos: Fecha Días Punta Resto Valle Punta Resto Valle
202308 202309 202310 202311 202312 202401 202402
R: Consumo real 1 - 29 3,4217 3,3098 3,2457
E: Consumo estimado Punta: 1035 1073 1042 1040 1069 1046 508 2 - 0 0,0000 0,0000 0,0000
Fuera Punta: 1053 1044 1055 1057 1062 1073 529 3 - 0 0,0000 0,0000 0,0000
29 3,4217 3,3098 3,2457
Factor de Potencia:
Concepto Punta Valle Resto
Tg. Fi.: 0,196 0,191 0,195
Total de energía activa: 202122KWh
Recargo:
Lecturas
Nº Medidor Concepto: Cte. Consumo Detalle de Facturación Importe:
Anterior: Actual:
SUBTOTAL IMPUESTOS 1.136.980,82
Tasa de iluminacion municipal - La Plata 30.000,00
SUBTOTAL CARGOS VARIOS EXENTOS 30.000,00
Su gasto diario de electricidad es de $ 102940,51 Vencimientos Recargo
1º 11/03/2024 4.325.173,17
Próximo Vencimiento: 08/04/2024
I.V.A. del recargo: 29175,65 2º 18/03/2024 146.959,92 4.472.133,09
Página nº 2de 2
Remite Sucursal: CITY BELL
14 364 1896 CITY BELL - Tel.: 4722923
Período: 202402 Nº de factura:0020-01766800
Información Complementaria: Tarifa: T5M12 - Media Tension NIR: 0-3512065-01-01/03/2024
Esta factura incluye Subsidio Estado Nacional por $0 Vencimientos Recargo Importe:
1º 11/03/2024 4.325.173,17
2º 18/03/2024 146.959,92 4.472.133,09
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
    alto = max(1600, 13 * len(lineas) + 50)
    c = canvas.Canvas(ruta, pagesize=(2200, alto))
    c.setFont("Helvetica", 9)
    y = alto - 50
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


def test_edelap_factura_202402_sin_exceso_usa_demanda_registrada(tmp_path):
    """Mes sin exceso: la demanda registrada (508/529 kW) queda por debajo de la contratada. Derivarla
    de contratada + exceso daría 800/850 kW, y exigir los 4 conceptos tarifados rechazaba la factura."""
    ruta_pdf = str(tmp_path / "edelap_202402.pdf")
    _generar_pdf(ruta_pdf, LINEAS_EDELAP_202402)

    factura = ParserFacturaPotenciaEdelap().parsear(ruta_pdf, PLANTA_ID)

    assert factura.periodo == "2024-02"
    assert factura.numero_factura == "0020-01766800"
    assert factura.dias_facturados == 29
    assert factura.potencia_contratada_punta_kw == pytest.approx(800.0)
    assert factura.potencia_contratada_fuera_punta_kw == pytest.approx(850.0)
    assert factura.potencia_adquirida_punta_kw == pytest.approx(508.0)
    # Fuera de punta = máx(resto 529, valle 517).
    assert factura.potencia_adquirida_fuera_punta_kw == pytest.approx(529.0)
    assert factura.potencia_excedida_punta_kw == pytest.approx(0.0)
    assert factura.potencia_excedida_fuera_punta_kw == pytest.approx(0.0)
    # Solo pico + fuera de pico por transporte: ni el interés por mora ni el CTT.
    assert factura.importe_potencia_ars == pytest.approx(1304243.38 + 1009978.80)
    assert factura.importe_total_ars == pytest.approx(4325173.17)


def _registrada(factura) -> tuple:
    return (
        factura.energia_registrada_punta_kwh,
        factura.energia_registrada_resto_kwh,
        factura.energia_registrada_valle_kwh,
        factura.energia_registrada_total_kwh,
    )


def _reactiva(factura) -> tuple:
    return (
        factura.energia_reactiva_punta_kvarh,
        factura.energia_reactiva_resto_kvarh,
        factura.energia_reactiva_valle_kvarh,
    )


def _parsear(tmp_path, lineas: list[str]):
    ruta_pdf = str(tmp_path / "edelap.pdf")
    _generar_pdf(ruta_pdf, lineas)
    return ParserFacturaPotenciaEdelap().parsear(ruta_pdf, PLANTA_ID)


def _variante(lineas: list[str], viejo: str, nuevo: str | None) -> list[str]:
    """Deriva del fixture literal una variante que cambia (o quita, con `nuevo=None`) UN token
    puntual; el resto del texto sigue siendo el real, no se retipea."""
    tocadas = [i for i, linea in enumerate(lineas) if viejo in linea]
    assert len(tocadas) == 1, f"'{viejo}' tiene que estar en una sola línea del fixture"
    i = tocadas[0]
    if nuevo is None:
        return lineas[:i] + lineas[i + 1 :]
    return [*lineas[:i], lineas[i].replace(viejo, nuevo), *lineas[i + 1 :]]


def test_edelap_202411_extrae_la_energia_registrada_sin_energia_facturada(tmp_path):
    """Bloque "Lecturas" del medidor 241609298. `extract_text()` pega en la misma línea la columna
    de cargos de otro renglón (la fila de reactiva punta trae "59994 kWh", el cargo de valle): solo
    se lee hasta la marca "R". Decisión 2026-09-28 D1/D2: nada de esto es energía facturada."""
    factura = _parsear(tmp_path, LINEAS_EDELAP_202411)

    assert _registrada(factura) == (68310.0, 187506.0, 59994.0, 315810.0)
    assert _reactiva(factura) == (29538.0, 83304.0, 23202.0)
    assert factura.energia_facturada_kwh is None
    assert factura.energia_activa_punta_kwh is None
    assert factura.energia_activa_total_kwh is None
    assert factura.importe_energia_ars is None


def test_edelap_202312_extrae_la_energia_registrada(tmp_path):
    factura = _parsear(tmp_path, LINEAS_EDELAP_202312)

    assert _registrada(factura) == (76914.0, 191304.0, 90954.0, 359172.0)
    assert _reactiva(factura) == (37152.0, 92034.0, 44730.0)


def test_edelap_202402_suma_las_filas_duplicadas_por_cambio_de_medidor(tmp_path):
    """2024-02 trae cada fila dos veces (una con consumo 0) y el total impreso dos veces. La
    energía se acumula, así que se suma por franja; la potencia, en cambio, toma el máximo."""
    factura = _parsear(tmp_path, LINEAS_EDELAP_202402)

    assert _registrada(factura) == (47826.0, 103086.0, 51210.0, 202122.0)
    assert _reactiva(factura) == (9378.0, 20124.0, 9792.0)


def test_edelap_marca_de_lectura_distinta_de_r_lanza_ilegible(tmp_path):
    """Una marca que no es "R" (lectura real) puede ser un consumo estimado: no se adivina."""
    lineas = _variante(LINEAS_EDELAP_202411, "18.000 68310 R Cargo", "18.000 68310 E Cargo")

    with pytest.raises(FacturaDistribuidoraIlegibleError, match="marca"):
        _parsear(tmp_path, lineas)


def test_edelap_suma_de_franjas_distinta_del_total_impreso_lanza_ilegible(tmp_path):
    """D6: punta + resto + valle tiene que dar el "Total de energía activa" impreso."""
    lineas = _variante(LINEAS_EDELAP_202411, "activa: 315810KWh", "activa: 315811KWh")

    with pytest.raises(FacturaDistribuidoraIlegibleError, match="315811"):
        _parsear(tmp_path, lineas)


def test_edelap_sin_una_franja_de_energia_activa_lanza_ilegible(tmp_path):
    lineas = _variante(LINEAS_EDELAP_202411, "241609298 Energia activa valle", None)

    with pytest.raises(FacturaDistribuidoraIlegibleError, match="valle"):
        _parsear(tmp_path, lineas)


def test_edelap_fila_de_lectura_de_energia_mal_formada_lanza_ilegible(tmp_path):
    """Sin la constante, la fila no tiene la forma medidor · concepto · anterior · actual ·
    constante · consumo · marca: se rechaza en vez de saltearla."""
    lineas = _variante(LINEAS_EDELAP_202411, "132120 18.000 68310 R", "132120 68310 R")

    with pytest.raises(FacturaDistribuidoraIlegibleError, match="Energia activa punta"):
        _parsear(tmp_path, lineas)


def test_edelap_factura_que_no_informa_la_energia_deja_los_campos_en_none(tmp_path):
    """D3: la registrada va "si la factura la informa". Sin filas de lectura de energía ni total
    impreso, los campos quedan en None y la potencia se sigue leyendo."""
    lineas = [
        linea
        for linea in LINEAS_EDELAP_202411
        if not linea.startswith("241609298 Energia") and not linea.startswith("Total de energía activa")
    ]

    factura = _parsear(tmp_path, lineas)

    assert _registrada(factura) == (None, None, None, None)
    assert _reactiva(factura) == (None, None, None)
    assert factura.potencia_adquirida_punta_kw == pytest.approx(1049.0)


def test_edelap_total_impreso_sin_filas_de_lectura_lanza_ilegible(tmp_path):
    lineas = [linea for linea in LINEAS_EDELAP_202411 if not linea.startswith("241609298 Energia")]

    with pytest.raises(FacturaDistribuidoraIlegibleError):
        _parsear(tmp_path, lineas)


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


PALABRAS_CAMMESA_UPP_202410_INTEGRAL = [
    ("0057-00323139", 430, 67),
    ("Periodo", 100, 197),
    ("01/10/2024", 250, 197),
    ("31/10/2024", 400, 197),
    ("300,960", 50, 285),
    ("MWh", 120, 285),
    ("Energía", 180, 285),
    ("Demandada", 250, 285),
    ("SUBTOTAL", 50, 296),
    ("ENERGÍA", 150, 296),
    ("DEMANDADA", 250, 296),
    ("3.117.344", 480, 296),
    ("1,089", 50, 307),
    ("MW", 100, 307),
    ("Cargos", 150, 307),
    ("de", 200, 307),
    ("Potencia", 230, 307),
    ("SUBTOTAL", 50, 318),
    ("CARGOS", 130, 318),
    ("DE", 190, 318),
    ("POTENCIA", 230, 318),
    ("3.079.473", 480, 318),
    ("CARGOS", 50, 328),
    ("ADICIONALES", 120, 328),
    ("DEL", 210, 328),
    ("MEM", 250, 328),
    ("14.419.642", 480, 328),
    ("CARGOS", 50, 361),
    ("RES.MEyM", 130, 361),
    ("281", 200, 361),
    ("110.275", 480, 361),
    ("ACTIVIDAD", 50, 372),
    ("MERCADO", 130, 372),
    ("39.190", 480, 372),
    ("SUBTOTAL", 50, 383),
    ("CARGOS", 130, 383),
    ("TRANSPORTE", 200, 383),
    ("1.785.216", 480, 383),
    ("SUBTOTAL", 250, 475),
    ("22.551.140,00", 480, 475),
    ("I.V.A.", 200, 487),
    ("RESP.", 250, 487),
    ("6.088.807,80", 480, 487),
    ("I.V.A.", 200, 499),
    ("PERCEPCION", 250, 499),
    ("676.534,20", 480, 499),
    ("LEY", 200, 510),
    ("24065", 250, 510),
    ("215.788,32", 480, 510),
    ("TOTAL", 200, 550),
    ("29.532.270,32", 480, 550),
]


def test_cammesa_factura_202410_extrae_desglose_completo_con_palabras(tmp_path):
    ruta_pdf = str(tmp_path / "cammesa_202410.pdf")
    _generar_pdf_por_palabras(ruta_pdf, PALABRAS_CAMMESA_UPP_202410_INTEGRAL)

    factura = ParserFacturaEnergiaCammesa().parsear(ruta_pdf, PLANTA_ID)

    assert factura.periodo == "2024-10"
    assert factura.numero_factura == "0057-00323139"
    assert factura.energia_activa_total_kwh == pytest.approx(300960.0)
    assert factura.importe_energia_ars == pytest.approx(3117344.0)
    assert factura.potencia_adquirida_mem_kw == pytest.approx(1089.0)
    assert factura.importe_potencia_mem_ars == pytest.approx(3079473.0)
    assert factura.importe_adicionales_mem_ars == pytest.approx(14419642.0)
    assert factura.importe_transporte_mem_ars == pytest.approx(1785216.0)
    assert factura.importe_otros_cargos_mem_ars == pytest.approx(149465.0)
    assert factura.importe_neto_ars == pytest.approx(22551140.0)
    assert factura.importe_impuestos_ars == pytest.approx(6981130.32)
    assert factura.importe_total_ars == pytest.approx(29532270.32)
    assert factura.valor_energia_integral_ars_kwh == pytest.approx(22551140.0 / 300960.0)


def test_cammesa_12_facturas_reales_extraen_desglose_y_balancean():
    import glob

    rutas = sorted(glob.glob("data/Papelera platense - CAMMESA/*.pdf"))
    assert len(rutas) == 12, "Deben existir exactamente 12 facturas reales de CAMMESA"

    parser = ParserFacturaEnergiaCammesa()
    for ruta in rutas:
        factura = parser.parsear(ruta, PLANTA_ID)
        assert factura.proveedor == "CAMMESA"
        assert factura.tipo_dato == "energia"
        assert factura.energia_activa_total_kwh is not None and factura.energia_activa_total_kwh > 0
        assert factura.importe_energia_ars is not None and factura.importe_energia_ars > 0
        assert factura.potencia_adquirida_mem_kw is not None and factura.potencia_adquirida_mem_kw > 0
        assert factura.importe_potencia_mem_ars is not None and factura.importe_potencia_mem_ars > 0
        assert factura.importe_adicionales_mem_ars is not None and factura.importe_adicionales_mem_ars > 0
        assert factura.importe_transporte_mem_ars is not None and factura.importe_transporte_mem_ars > 0
        assert factura.importe_neto_ars is not None and factura.importe_neto_ars > 0
        assert factura.importe_impuestos_ars is not None and factura.importe_impuestos_ars > 0
        assert factura.importe_total_ars > 0

        # Balanceo exacto: partidas netas suman el subtotal neto
        suma_partidas = (
            factura.importe_energia_ars
            + factura.importe_potencia_mem_ars
            + factura.importe_adicionales_mem_ars
            + factura.importe_transporte_mem_ars
            + (factura.importe_otros_cargos_mem_ars or 0.0)
        )
        assert factura.importe_neto_ars == pytest.approx(suma_partidas, abs=1.0)

        # Balanceo exacto: neto + impuestos suman el total
        assert factura.importe_total_ars == pytest.approx(
            factura.importe_neto_ars + factura.importe_impuestos_ars, abs=1.0
        )

        # Tarifa integral mayorista calculada
        assert factura.valor_energia_integral_ars_kwh is not None
        assert factura.valor_energia_integral_ars_kwh == pytest.approx(
            factura.importe_neto_ars / factura.energia_activa_total_kwh
        )

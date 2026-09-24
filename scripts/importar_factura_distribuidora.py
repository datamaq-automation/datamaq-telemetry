#!/usr/bin/env python3
"""Parsea una factura de la distribuidora en PDF y vuelca el bloque YAML resultante para
pegarlo en `data/facturas_distribuidora.yml` — con revisión humana antes de commitear, no
por escritura directa del servicio (`RepositorioOrganizacionesPort` es solo lectura).

No escribe nada. La salida es un borrador: revisar los valores extraídos contra el PDF
original antes de commitear (CONVENTIONS §3.6, dato físico declarativo sin fuente confirmada
no va al YAML).

Uso:
  venv/bin/python scripts/importar_factura_distribuidora.py <ruta_pdf> <planta_id>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.domain.telemetria.exceptions import FacturaDistribuidoraIlegibleError  # noqa: E402
from src.infrastructure.pdfplumber.parser_factura_distribuidora import (  # noqa: E402
    PdfplumberParserFacturaDistribuidora,
)


def _bloque_yaml(f) -> str:
    """Emite solo los campos poblados del documento (potencia O energía, nunca ambos a la vez:
    ver FacturaDistribuidora en domain/sge/entities.py)."""
    campos_str = [
        ("planta_id", f.planta_id),
        ("periodo", f.periodo),
        ("proveedor", f.proveedor),
        ("tipo_dato", f.tipo_dato),
        ("numero_factura", f.numero_factura),
    ]
    campos_num = [
        ("importe_total_ars", f.importe_total_ars),
        ("tarifa", f.tarifa),
        ("dias_facturados", f.dias_facturados),
        ("energia_activa_punta_kwh", f.energia_activa_punta_kwh),
        ("energia_activa_resto_kwh", f.energia_activa_resto_kwh),
        ("energia_activa_valle_kwh", f.energia_activa_valle_kwh),
        ("potencia_contratada_punta_kw", f.potencia_contratada_punta_kw),
        ("potencia_contratada_fuera_punta_kw", f.potencia_contratada_fuera_punta_kw),
        ("potencia_adquirida_punta_kw", f.potencia_adquirida_punta_kw),
        ("potencia_adquirida_fuera_punta_kw", f.potencia_adquirida_fuera_punta_kw),
        ("importe_potencia_ars", f.importe_potencia_ars),
        ("importe_energia_ars", f.importe_energia_ars),
    ]
    lineas = [
        f'  - {nombre}: "{valor}"' if i == 0 else f'    {nombre}: "{valor}"'
        for i, (nombre, valor) in enumerate(campos_str)
    ]
    lineas += [f"    {nombre}: {valor}" for nombre, valor in campos_num if valor is not None]
    if f.fuente_archivo is not None:
        lineas.append(f'    fuente_archivo: "{f.fuente_archivo}"')
    return "\n".join(lineas) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ruta_pdf", help="Ruta al PDF de la factura")
    parser.add_argument("planta_id", help="ID de la planta (data/organizaciones.yml)")
    args = parser.parse_args()

    try:
        factura = PdfplumberParserFacturaDistribuidora().parsear(args.ruta_pdf, args.planta_id)
    except FacturaDistribuidoraIlegibleError as e:
        print(f"[ERROR] No se pudo parsear la factura: {e}", file=sys.stderr)
        return 1

    print("# Revisar contra el PDF original antes de commitear a data/facturas_distribuidora.yml")
    print(_bloque_yaml(factura))
    return 0


if __name__ == "__main__":
    sys.exit(main())

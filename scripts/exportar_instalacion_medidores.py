#!/usr/bin/env python3
"""Vuelca los datos de instalación que hoy guarda MySQL en formato YAML, para pegarlos en
`data/organizaciones.yml` bajo `plantas[].medidores[]` — con fuente citada, no antes.

No escribe nada. La salida es un borrador: cada valor sale de la base, no de una placa ni
de un plano, así que antes de pegarlo hay que confirmarlo en campo (CONVENTIONS §3.6).
Los campos con valor por defecto del dominio (CONSUMO, R,S,T, T2, True) se marcan como
`# default` porque probablemente nadie los cargó a mano.

Uso:
  venv/bin/python scripts/exportar_instalacion_medidores.py [--planta PLANTA_ID]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.infrastructure.sqlalchemy.database import get_session_factory  # noqa: E402
from src.infrastructure.sqlalchemy.models import DeviceModel  # noqa: E402
from src.infrastructure.yaml.repositories.organizaciones_repository import (  # noqa: E402
    YamlOrganizacionesRepository,
)

DEFAULTS = {"installation_type": "CONSUMO", "phases_with_ct": "R,S,T", "categoria_tarifaria": "T2"}


def _linea(clave: str, valor, columna: str) -> str:
    marca = "  # default del dominio, probablemente nunca cargado" if DEFAULTS.get(columna) == valor else ""
    return f'            {clave}: "{valor}"{marca}'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--planta", help="Limitar a una planta (id del YAML)")
    args = parser.parse_args()

    yaml_repo = YamlOrganizacionesRepository()
    db = get_session_factory()()
    try:
        plantas = yaml_repo.listar_plantas()
        if args.planta:
            plantas = [p for p in plantas if p.id == args.planta]
        for planta in plantas:
            devices = (
                db.query(DeviceModel).filter(DeviceModel.facility_id == planta.id).order_by(DeviceModel.name).all()
            )
            if not devices:
                continue
            print(f"# {planta.nombre} ({planta.id}) — BORRADOR exportado de MySQL, confirmar en campo antes de pegar")
            print("        medidores:")
            for d in devices:
                print(f'          - id: "{d.id}"  # {d.name} · MAC {d.device_uid}')
                if d.tag_location:
                    print(_linea("tag_ubicacion", d.tag_location, "tag_location"))
                print(_linea("tipo_instalacion", d.installation_type, "installation_type"))
                print(_linea("fases_con_ti", d.phases_with_ct, "phases_with_ct"))
            print("        # Contrato: va en el nodo `acometida` del unifilar, no por medidor:")
            tarifas = {(d.categoria_tarifaria, d.penalizacion_reactiva_aplica) for d in devices}
            for cat, pen in sorted(tarifas, key=str):
                marca = "  # default del dominio" if cat == "T2" and pen else ""
                print(
                    f'        #   categoria_tarifaria: "{cat}"  /  penalizacion_reactiva_aplica: {str(pen).lower()}{marca}'
                )
            print()
    finally:
        db.close()


if __name__ == "__main__":
    main()

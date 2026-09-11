#!/usr/bin/env python3
"""Script de aprovisionamiento rápido para la Planta y Confeccionadora de Bolsas en la VPS.

Uso:
  python3 scripts/provision_confeccionadora.py \
      --smartplus-mac AABBCCDDEEFF \
      --automate-id 112233445566 \
      [--org "Cliente Confecciones"] \
      [--planta "Planta Principal"] \
      [--maquina "Confeccionadora de Bolsas"]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.dtos.dispositivo_dto import DispositivoCreateDTO  # noqa: E402
from src.application.dtos.maquina_dto import MaquinaCreateDTO  # noqa: E402
from src.application.dtos.organizacion_dto import OrganizacionCreateDTO, PlantaCreateDTO  # noqa: E402
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase  # noqa: E402
from src.application.use_cases.gestionar_maquinas import GestionarMaquinasUseCase  # noqa: E402
from src.domain.telemetria.value_objects import MacAddress  # noqa: E402
from src.infrastructure.sqlalchemy.database import get_session_factory  # noqa: E402
from src.infrastructure.sqlalchemy.mysql_repositories import (  # noqa: E402
    MySQLDispositivosRepository,
    MySQLMaquinasRepository,
    MySQLOrganizacionesRepository,
)


def _normalizar_mac(mac: str) -> str:
    limpio = mac.replace(":", "").replace("-", "").upper()
    if len(limpio) < 12:
        limpio = limpio.zfill(12)
    elif len(limpio) > 12:
        limpio = limpio[-12:]
    return limpio


def provisionar_planta_y_maquina(
    smartplus_mac: str,
    automate_id: str,
    org_nombre: str = "Cliente Confecciones",
    planta_nombre: str = "Planta Principal",
    maquina_nombre: str = "Confeccionadora de Bolsas",
    dry_run: bool = False,
) -> None:
    session_factory = get_session_factory()
    db = session_factory()
    try:
        repo_orgs = MySQLOrganizacionesRepository(db)
        repo_devs = MySQLDispositivosRepository(db)
        repo_maquinas = MySQLMaquinasRepository(db)

        use_case_devs = GestionarDispositivosUseCase(
            repo_dispositivos=repo_devs,
            repo_organizaciones=repo_orgs,
        )
        use_case_maquinas = GestionarMaquinasUseCase(
            repo_maquinas=repo_maquinas,
            repo_dispositivos=repo_devs,
        )

        # 1. Organización
        orgs = repo_orgs.listar_organizaciones()
        org = next((o for o in orgs if o.nombre == org_nombre), None)
        if org:
            print(f"[=] Organización existente: '{org_nombre}' ({org.id})")
            org_id = org.id
        else:
            if dry_run:
                print(f"[DRY] Crearía Organización '{org_nombre}'")
                org_id = "DRY-ORG-ID"
            else:
                nueva_org = use_case_devs.crear_organizacion(OrganizacionCreateDTO(nombre=org_nombre))
                org_id = nueva_org.id
                print(f"[+] Organización creada: '{org_nombre}' ({org_id})")

        # 2. Planta
        plantas = repo_orgs.listar_plantas(organizacion_id=org_id)
        planta = next((p for p in plantas if p.nombre == planta_nombre), None)
        if planta:
            print(f"[=] Planta existente: '{planta_nombre}' ({planta.id})")
            planta_id = planta.id
        else:
            if dry_run:
                print(f"[DRY] Crearía Planta '{planta_nombre}'")
                planta_id = "DRY-PLANTA-ID"
            else:
                nueva_planta = use_case_devs.crear_planta(PlantaCreateDTO(organizacion_id=org_id, nombre=planta_nombre))
                planta_id = nueva_planta.id
                print(f"[+] Planta creada: '{planta_nombre}' ({planta_id})")

        # 3. Dispositivo Smart Plus
        sp_mac_norm = _normalizar_mac(smartplus_mac)
        sp_vo = MacAddress(sp_mac_norm)
        sp_dev = repo_devs.obtener_por_uid(sp_vo)
        if sp_dev:
            print(f"[=] Dispositivo Smart Plus ya existe: MAC {sp_mac_norm}")
            sp_dev_id = sp_dev.id
        else:
            if dry_run:
                print(f"[DRY] Crearía Smart Plus MAC {sp_mac_norm}")
                sp_dev_id = "DRY-SP-DEV-ID"
            else:
                sp_dto = DispositivoCreateDTO(
                    device_uid=sp_mac_norm,
                    nombre=f"SmartPlus-{sp_mac_norm[-4:]}",
                    modelo="SmartPlus",
                    planta_id=planta_id,
                )
                sp_creado = use_case_devs.registrar_dispositivo(sp_dto)
                sp_dev_id = sp_creado.id
                print(f"[+] Smart Plus registrado: MAC {sp_mac_norm} ({sp_dev_id})")

        # 4. Dispositivo Automate 24V-4M
        aut_mac_norm = _normalizar_mac(automate_id)
        aut_vo = MacAddress(aut_mac_norm)
        aut_dev = repo_devs.obtener_por_uid(aut_vo)
        if aut_dev:
            print(f"[=] Dispositivo Automate ya existe: ID {aut_mac_norm}")
            aut_dev_id = aut_dev.id
        else:
            if dry_run:
                print(f"[DRY] Crearía Automate ID {aut_mac_norm}")
                aut_dev_id = "DRY-AUT-DEV-ID"
            else:
                aut_dto = DispositivoCreateDTO(
                    device_uid=aut_mac_norm,
                    nombre=f"Automate-{aut_mac_norm[-4:]}",
                    modelo="Automate24V4M",
                    planta_id=planta_id,
                )
                aut_creado = use_case_devs.registrar_dispositivo(aut_dto)
                aut_dev_id = aut_creado.id
                print(f"[+] Automate registrado: ID {aut_mac_norm} ({aut_dev_id})")

        # 5. Máquina Confeccionadora de Bolsas (asociada al Smart Plus)
        maquinas = repo_maquinas.listar_maquinas()
        maq = next((m for m in maquinas if m.nombre == maquina_nombre), None)
        if maq:
            print(f"[=] Máquina existente: '{maquina_nombre}' ({maq.id})")
        else:
            if dry_run:
                print(f"[DRY] Crearía Máquina '{maquina_nombre}'")
            else:
                maq_dto = MaquinaCreateDTO(
                    nombre=maquina_nombre,
                    dispositivo_id=sp_dev_id,
                    umbral_marcha_w=100.0,
                )
                nueva_maq = use_case_maquinas.registrar_maquina(maq_dto, organizacion_id=org_id)
                print(f"[+] Máquina creada: '{maquina_nombre}' ({nueva_maq.id}) vinculada a Smart Plus {sp_mac_norm}")

        print("[OK] Alta y aprovisionamiento de Planta y Confeccionadora completados con éxito.")

    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Alta rápida de Planta, Confeccionadora, SmartPlus y Automate")
    parser.add_argument("--smartplus-mac", required=True, help="MAC address del Smart Plus (ej: AABBCCDDEEFF)")
    parser.add_argument("--automate-id", required=True, help="ID/MAC address del Automate 24V-4M (ej: 112233445566)")
    parser.add_argument("--org", default="Cliente Confecciones", help="Nombre de la Organización")
    parser.add_argument("--planta", default="Planta Principal", help="Nombre de la Planta")
    parser.add_argument("--maquina", default="Confeccionadora de Bolsas", help="Nombre de la Máquina")
    parser.add_argument("--dry-run", action="store_true", help="Simular sin escribir en la base de datos")

    args = parser.parse_args()
    provisionar_planta_y_maquina(
        smartplus_mac=args.smartplus_mac,
        automate_id=args.automate_id,
        org_nombre=args.org,
        planta_nombre=args.planta,
        maquina_nombre=args.maquina,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Script idempotente de alta de cliente en Datamaq Telemetry.

Crea (o verifica que existan) los siguientes recursos en orden:
  1. Organización
  2. Planta
  3. Usuario operador
  4. N x Dispositivos (por MAC address)

Uso:
  venv/bin/python scripts/seed_cliente.py \\
    --org-nombre "Vajillas Durax S.A." \\
    --planta-nombre "Planta Principal Durax" \\
    --usuario "instrumental@vajillasdurax.com.ar" \\
    --password-env DURAX_PASSWORD \\
    --dispositivo "AA:BB:CC:DD:EE:01" "SmartPlus Trifásico #1" \\
    --dispositivo "AA:BB:CC:DD:EE:02" "SmartPlus Trifásico #2"

Para el medidor domiciliario existente sin planta asignada:
  venv/bin/python scripts/seed_cliente.py \\
    --org-nombre "Datamaq Uso Interno" \\
    --planta-nombre "Domicilio Agustín" \\
    --asignar-dispositivo-existente D48C49F03564
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.dtos.dispositivo_dto import DispositivoCreateDTO  # noqa: E402
from src.application.dtos.organizacion_dto import (  # noqa: E402
    OrganizacionCreateDTO,
    PlantaCreateDTO,
)
from src.application.use_cases.gestionar_dispositivos import (  # noqa: E402
    GestionarDispositivosUseCase,
)
from src.application.use_cases.gestionar_usuarios import GestionarUsuariosUseCase  # noqa: E402
from src.domain.auth.services import HashContrasenaService  # noqa: E402
from src.infrastructure.sqlalchemy.database import get_session_factory  # noqa: E402
from src.infrastructure.sqlalchemy.models import DeviceModel  # noqa: E402
from src.infrastructure.sqlalchemy.mysql_repositories import (  # noqa: E402
    MySQLDispositivosRepository,
    MySQLOrganizacionesRepository,
    MySQLUsuariosRepository,
)


@dataclass
class DispositivoArg:
    mac: str
    nombre: str


def _normalizar_mac(mac: str) -> str:
    """Quita separadores y convierte a mayúsculas: 'AA:BB:CC:DD:EE:01' → 'AABBCCDDEE01'."""
    return mac.replace(":", "").replace("-", "").upper()


def _obtener_password(password_env: str | None) -> str:
    if password_env:
        pwd = os.environ.get(password_env)
        if pwd:
            return pwd
        print(
            f"[!] ADVERTENCIA: variable de entorno '{password_env}' no definida.",
            file=sys.stderr,
        )
    pwd = os.environ.get("CLIENTE_PASSWORD")
    if pwd:
        return pwd
    print(
        "[!] No se encontró contraseña. Definí la variable de entorno "
        "CLIENTE_PASSWORD o usa --password-env NOMBRE_VAR.",
        file=sys.stderr,
    )
    sys.exit(1)


def alta_cliente(
    org_nombre: str,
    planta_nombre: str,
    planta_direccion: str | None,
    usuario_email: str | None,
    password: str | None,
    dispositivos: list[DispositivoArg],
    dispositivos_existentes: list[str],
    org_cuit: str | None,
    org_email_contacto: str | None,
    dry_run: bool,
) -> None:
    session_factory = get_session_factory()
    db = session_factory()
    try:
        repo_orgs = MySQLOrganizacionesRepository(db)
        repo_devs = MySQLDispositivosRepository(db)
        repo_users = MySQLUsuariosRepository(db)

        use_case_devs = GestionarDispositivosUseCase(
            repo_dispositivos=repo_devs,
            repo_organizaciones=repo_orgs,
        )
        use_case_users = GestionarUsuariosUseCase(repo_users, HashContrasenaService())

        # ── 1. Organización ────────────────────────────────────────────────
        orgs_existentes = repo_orgs.listar_organizaciones()
        org_existente = next((o for o in orgs_existentes if o.nombre == org_nombre), None)

        if org_existente:
            print(f"[=] Organización ya existe: '{org_nombre}' (id={org_existente.id[:8]}...)")
            org_id = org_existente.id
        else:
            if dry_run:
                print(f"[DRY] Crearía organización: '{org_nombre}'")
                org_id = "DRY-ORG-ID"
            else:
                org_dto = OrganizacionCreateDTO(
                    nombre=org_nombre,
                    cuit=org_cuit,
                    email_contacto=org_email_contacto,
                )
                org_creada = use_case_devs.crear_organizacion(org_dto)
                org_id = org_creada.id
                print(f"[+] Organización creada: '{org_nombre}' (id={org_id[:8]}...)")

        # ── 2. Planta ──────────────────────────────────────────────────────
        plantas_existentes = repo_orgs.listar_plantas(organizacion_id=org_id)
        planta_existente = next((p for p in plantas_existentes if p.nombre == planta_nombre), None)

        if planta_existente:
            print(f"[=] Planta ya existe: '{planta_nombre}' (id={planta_existente.id[:8]}...)")
            planta_id = planta_existente.id
        else:
            if dry_run:
                print(f"[DRY] Crearía planta: '{planta_nombre}' en org '{org_nombre}'")
                planta_id = "DRY-PLANTA-ID"
            else:
                planta_dto = PlantaCreateDTO(
                    organizacion_id=org_id,
                    nombre=planta_nombre,
                    direccion=planta_direccion,
                )
                planta_creada = use_case_devs.crear_planta(planta_dto)
                planta_id = planta_creada.id
                print(f"[+] Planta creada: '{planta_nombre}' (id={planta_id[:8]}...)")

        # ── 3. Usuario operador ────────────────────────────────────────────
        if usuario_email and password:
            usuario_existente = repo_users.obtener_por_usuario(usuario_email)
            if usuario_existente:
                print(f"[=] Usuario ya existe: '{usuario_email}' (rol={usuario_existente.rol})")
            elif dry_run:
                print(f"[DRY] Crearía usuario: '{usuario_email}' (rol=operador)")
            else:
                usuario_creado = use_case_users.crear_usuario(
                    usuario=usuario_email,
                    contrasena=password,
                    esta_activo=True,
                    rol="operador",
                    organizacion_id=org_id,
                )
                print(
                    f"[+] Usuario creado: '{usuario_creado.usuario}' "
                    f"(rol={usuario_creado.rol}, id={usuario_creado.id[:8]}...)"
                )

        # ── 4. Nuevos dispositivos ─────────────────────────────────────────
        for dev_arg in dispositivos:
            mac_norm = _normalizar_mac(dev_arg.mac)
            dev_model = db.query(DeviceModel).filter(DeviceModel.device_uid == mac_norm).first()
            if dev_model:
                print(
                    f"[=] Dispositivo '{dev_arg.mac}' ya existe "
                    f"(nombre='{dev_model.name}', planta={dev_model.facility_id})"
                )
            elif dry_run:
                print(
                    f"[DRY] Crearía dispositivo: MAC={mac_norm} nombre='{dev_arg.nombre}' en planta '{planta_nombre}'"
                )
            else:
                dev_dto = DispositivoCreateDTO(
                    device_uid=mac_norm,
                    nombre=dev_arg.nombre,
                    modelo="SmartPlus",
                    planta_id=planta_id,
                    tipo_instalacion="CONSUMO",
                    fases_con_ti="R,S,T",
                )
                dev_creado = use_case_devs.registrar_dispositivo(dev_dto)
                print(
                    f"[+] Dispositivo registrado: '{dev_creado.nombre}' "
                    f"(uid={dev_creado.device_uid}, id={dev_creado.id[:8]}...)"
                )

        # ── 5. Asignar dispositivos existentes (sin planta) a esta planta ──
        for mac_raw in dispositivos_existentes:
            mac_norm = _normalizar_mac(mac_raw)
            model = db.query(DeviceModel).filter(DeviceModel.device_uid == mac_norm).first()
            if not model:
                print(
                    f"[!] Dispositivo con MAC '{mac_raw}' no encontrado en la BD.",
                    file=sys.stderr,
                )
                continue
            if model.facility_id == planta_id:
                print(f"[=] Dispositivo '{mac_raw}' ya está asignado a planta '{planta_nombre}'")
            elif dry_run:
                print(f"[DRY] Asignaría dispositivo '{mac_raw}' a planta '{planta_nombre}'")
            else:
                model.facility_id = planta_id
                db.commit()
                print(f"[+] Dispositivo '{mac_raw}' (nombre='{model.name}') asignado a planta '{planta_nombre}'")

    except Exception as e:
        print(f"[!] Error durante el alta: {e}", file=sys.stderr)
        if not dry_run:
            db.rollback()
        sys.exit(1)
    finally:
        db.close()


def _parse_dispositivo(valor: str) -> DispositivoArg:
    """Parsea 'MAC:Nombre del dispositivo' o 'MAC' solo."""
    partes = valor.split(":", maxsplit=6)
    # MAC puede ser AA:BB:CC:DD:EE:FF (6 partes) o sin separadores
    if len(partes) >= 6:
        mac = ":".join(partes[:6])
        nombre = partes[6] if len(partes) > 6 else mac
    else:
        mac = partes[0]
        nombre = partes[1] if len(partes) > 1 else mac
    return DispositivoArg(mac=mac.strip(), nombre=nombre.strip())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Alta idempotente de cliente en Datamaq Telemetry",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--org-nombre", required=True, help="Nombre de la organización")
    parser.add_argument("--org-cuit", help="CUIT de la organización (opcional)")
    parser.add_argument("--org-email", help="Email de contacto de la organización (opcional)")
    parser.add_argument("--planta-nombre", required=True, help="Nombre de la planta")
    parser.add_argument("--planta-direccion", help="Dirección física de la planta (opcional)")
    parser.add_argument("--usuario", help="Email del usuario operador a crear")
    parser.add_argument(
        "--password-env",
        help="Nombre de la variable de entorno con la contraseña del usuario",
    )
    parser.add_argument(
        "--dispositivo",
        nargs="+",
        action="append",
        metavar=("MAC", "NOMBRE"),
        help="MAC y nombre del dispositivo. Repetir para varios: --dispositivo AA:BB:... 'Nombre'",
    )
    parser.add_argument(
        "--asignar-dispositivo-existente",
        action="append",
        default=[],
        metavar="MAC",
        help="MAC de un dispositivo ya registrado a asignar a esta planta",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula las operaciones sin escribir en la BD",
    )
    args = parser.parse_args()

    # Contraseña
    password: str | None = None
    if args.usuario:
        password = _obtener_password(args.password_env)

    # Dispositivos nuevos
    dispositivos: list[DispositivoArg] = []
    if args.dispositivo:
        for grupo in args.dispositivo:
            if len(grupo) >= 2:
                dispositivos.append(DispositivoArg(mac=grupo[0].strip(), nombre=" ".join(grupo[1:]).strip()))
            else:
                dispositivos.append(_parse_dispositivo(grupo[0]))

    if args.dry_run:
        print("[DRY RUN] No se realizarán cambios en la base de datos.")

    alta_cliente(
        org_nombre=args.org_nombre,
        planta_nombre=args.planta_nombre,
        planta_direccion=args.planta_direccion,
        usuario_email=args.usuario,
        password=password,
        dispositivos=dispositivos,
        dispositivos_existentes=args.asignar_dispositivo_existente,
        org_cuit=args.org_cuit,
        org_email_contacto=args.org_email,
        dry_run=args.dry_run,
    )

    print("\n[✓] Alta completada.")


if __name__ == "__main__":
    main()

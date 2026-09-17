#!/usr/bin/env python3
"""scripts/gestionar_usuario_organizacion.py — Script CLI para inspeccionar y asociar usuarios a organizaciones y plantas en producción."""

import argparse
import sys
from pathlib import Path

# Garantizar import de src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.domain.auth.entities import AccesoPlantaUsuario
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.repositories.accesos_planta_repository import MySQLAccesosPlantaRepository
from src.infrastructure.sqlalchemy.repositories.usuarios_repository import MySQLUsuariosRepository
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository


def main():
    parser = argparse.ArgumentParser(
        description="Gestión e inspección de asignación de usuarios a organizaciones y plantas."
    )
    parser.add_argument("--usuario", required=True, help="Email o nombre de usuario (ej: marcelosoruco22@gmail.com)")
    parser.add_argument(
        "--org-id", help="UUID de la organización a vincular (ej: 20857cb6-eff2-4bd4-8cb9-36e4c63bcee3)"
    )
    parser.add_argument("--planta-id", help="UUID de la planta a asignar (ej: 6a182b0f-6406-4bc2-adf3-a4d2754198af)")
    parser.add_argument("--rol", help="Actualizar rol del usuario (ej: operador, admin, mantenimiento)")
    parser.add_argument("--vincular", action="store_true", help="Aplica la vinculación especificada en la BD")

    args = parser.parse_args()

    yaml_repo = YamlOrganizacionesRepository("data")
    orgs_yaml = {o.id: o for o in yaml_repo.listar_organizaciones()}

    sf = get_session_factory()
    with sf() as session:
        repo_usuarios = MySQLUsuariosRepository(session)
        repo_accesos = MySQLAccesosPlantaRepository(session)

        usr = repo_usuarios.obtener_por_usuario(args.usuario)
        if not usr:
            print(f"❌ Usuario '{args.usuario}' no encontrado en la base de datos.")
            sys.exit(1)

        print(f"👤 Usuario: {usr.usuario} (ID: {usr.id})")
        print(f"   Rol actual: {usr.rol}")
        print(f"   Organización actual: {usr.organizacion_id or 'NINGUNA (NULL)'}")

        if usr.organizacion_id and usr.organizacion_id in orgs_yaml:
            print(f"   Nombre Org: {orgs_yaml[usr.organizacion_id].nombre}")

        accesos_actuales = repo_accesos.listar_por_usuario(usr.id)
        print(f"   Plantas asignadas ({len(accesos_actuales)}):")
        for acc in accesos_actuales:
            planta_info = yaml_repo.obtener_planta_por_id(acc.planta_id)
            nombre_planta = planta_info.nombre if planta_info else "Desconocida"
            print(f"     - {acc.planta_id} ({nombre_planta}) [puede_cambiar={acc.puede_cambiar}]")

        if not args.vincular:
            print("\n[INFO] Para aplicar cambios de vinculación, use el flag --vincular con --org-id y/o --planta-id.")
            return

        # Aplicar vinculación
        cambios = False
        nuevo_org_id = usr.organizacion_id
        nuevo_rol = usr.rol

        if args.org_id:
            if args.org_id not in orgs_yaml:
                print(f"⚠️ Advertencia: org-id '{args.org_id}' no se encuentra en data/organizaciones.yml")
            nuevo_org_id = args.org_id
            cambios = True

        if args.rol:
            nuevo_rol = args.rol
            cambios = True

        if cambios:
            usr_actualizado = usr.copy_with(organizacion_id=nuevo_org_id, rol=nuevo_rol)
            repo_usuarios.guardar(usr_actualizado)
            print(f"✅ Usuario actualizado: organizacion_id={nuevo_org_id}, rol={nuevo_rol}")

        if args.planta_id:
            planta_valida = yaml_repo.obtener_planta_por_id(args.planta_id)
            if not planta_valida:
                print(f"⚠️ Advertencia: planta-id '{args.planta_id}' no se encuentra en data/organizaciones.yml")
            nuevos_accesos = list(accesos_actuales)
            if not any(a.planta_id == args.planta_id for a in nuevos_accesos):
                nuevos_accesos.append(
                    AccesoPlantaUsuario(usuario_id=usr.id, planta_id=args.planta_id, puede_cambiar=True)
                )
                repo_accesos.reemplazar(usr.id, nuevos_accesos)
                print(f"✅ Planta {args.planta_id} asignada a {usr.usuario}")
            else:
                print(f"[INFO] La planta {args.planta_id} ya estaba asignada.")

        session.commit()
        print("🎉 Proceso finalizado y cambios guardados en la BD.")


if __name__ == "__main__":
    main()

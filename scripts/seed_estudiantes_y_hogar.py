"""Crea las dos cuentas de solo lectura pedidas:

- invitado@datamaq.com.ar (rol "invitado"): solo ve el medidor doméstico D48C49F03564,
  vía la organización/planta "Hogar" declarada en data/organizaciones.yml.
- estudiantes@datamaq.com.ar (rol "invitado_global"): ve todos los medidores de todas
  las organizaciones, sin poder escribir nada (bloqueado por requiere_rol_escritura).

Idempotente: se puede correr varias veces sin duplicar datos.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.dtos.dispositivo_dto import DispositivoUpdateDTO
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.application.use_cases.gestionar_usuarios import GestionarUsuariosUseCase
from src.domain.auth.services import HashContrasenaService
from src.domain.telemetria.entities import Organizacion, Planta
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.models import FacilityModel, OrganizationModel
from src.infrastructure.sqlalchemy.repositories.dispositivos_repository import MySQLDispositivosRepository
from src.infrastructure.sqlalchemy.repositories.usuarios_repository import MySQLUsuariosRepository
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

USUARIO_HOGAR = "invitado@datamaq.com.ar"
USUARIO_ESTUDIANTES = "estudiantes@datamaq.com.ar"
DEVICE_UID_HOGAR = "D48C49F03564"
ORG_HOGAR_NOMBRE = "Hogar (medidor doméstico)"
PLANTA_HOGAR_NOMBRE = "Casa"


def obtener_org_hogar(repo_org: YamlOrganizacionesRepository) -> Organizacion:
    for org in repo_org.listar_organizaciones():
        if org.nombre == ORG_HOGAR_NOMBRE:
            return org
    print(f"[!] La organización '{ORG_HOGAR_NOMBRE}' no está en data/organizaciones.yml", file=sys.stderr)
    sys.exit(1)


def obtener_planta_hogar(repo_org: YamlOrganizacionesRepository, organizacion_id: str) -> Planta:
    for planta in repo_org.listar_plantas(organizacion_id):
        if planta.nombre == PLANTA_HOGAR_NOMBRE:
            return planta
    print(f"[!] La planta '{PLANTA_HOGAR_NOMBRE}' no está declarada en data/organizaciones.yml", file=sys.stderr)
    sys.exit(1)


def asegurar_filas_espejo(db, org: Organizacion, planta: Planta) -> None:
    """`users.organization_id` y `devices.facility_id` tienen FK a MySQL: se crea el ancla con el id del YAML."""
    if db.query(OrganizationModel).filter(OrganizationModel.id == org.id).first() is None:
        db.add(OrganizationModel(id=org.id, name=org.nombre))
    if db.query(FacilityModel).filter(FacilityModel.id == planta.id).first() is None:
        db.add(FacilityModel(id=planta.id, organization_id=org.id, name=planta.nombre))
    db.commit()


def asegurar_dispositivo_en_planta(
    use_case_dispositivos: GestionarDispositivosUseCase, repo_dispositivos, planta_id: str
) -> None:
    dispositivo = repo_dispositivos.obtener_por_id(DEVICE_UID_HOGAR)
    if dispositivo is None:
        from src.domain.telemetria.value_objects import MacAddress

        dispositivo = repo_dispositivos.obtener_por_uid(MacAddress(DEVICE_UID_HOGAR))
    if dispositivo is None:
        print(f"[!] No se encontró el dispositivo {DEVICE_UID_HOGAR}", file=sys.stderr)
        sys.exit(1)
    if dispositivo.planta_id == planta_id:
        return
    dto = DispositivoUpdateDTO(
        nombre=None,
        ubicacion_tag=None,
        numero_serie=None,
        tipo_instalacion=None,
        fases_con_ti=None,
        esta_activo=None,
        planta_id=planta_id,
    )
    use_case_dispositivos.actualizar_dispositivo(dispositivo.id, dto)


def obtener_contrasena(env_var: str, default: str) -> str:
    contrasena = os.environ.get(env_var)
    if contrasena:
        return contrasena
    print(
        f"[!] ADVERTENCIA: usando la contraseña por defecto '{default}' para {env_var}. "
        "Definila como variable de entorno en producción.",
        file=sys.stderr,
    )
    return default


def main() -> None:
    session_factory = get_session_factory()
    db = session_factory()
    try:
        repo_usuarios = MySQLUsuariosRepository(db)
        repo_org = YamlOrganizacionesRepository()
        repo_dispositivos = MySQLDispositivosRepository(db)
        use_case_usuarios = GestionarUsuariosUseCase(repo_usuarios, HashContrasenaService())
        use_case_dispositivos = GestionarDispositivosUseCase(repo_dispositivos, repo_org)

        org_hogar = obtener_org_hogar(repo_org)
        planta_hogar = obtener_planta_hogar(repo_org, org_hogar.id)
        asegurar_filas_espejo(db, org_hogar, planta_hogar)
        asegurar_dispositivo_en_planta(use_case_dispositivos, repo_dispositivos, planta_hogar.id)

        contrasena_hogar = obtener_contrasena("GUEST_HOGAR_PASSWORD", "invitado")
        usuario_hogar = use_case_usuarios.crear_usuario(
            USUARIO_HOGAR,
            contrasena_hogar,
            esta_activo=True,
            rol="invitado",
            organizacion_id=org_hogar.id,
        )
        print(f"[+] Usuario listo: {usuario_hogar.usuario} (rol={usuario_hogar.rol}, org={org_hogar.nombre})")

        contrasena_estudiantes = obtener_contrasena("GUEST_ESTUDIANTES_PASSWORD", "estudiantes")
        usuario_estudiantes = use_case_usuarios.crear_usuario(
            USUARIO_ESTUDIANTES,
            contrasena_estudiantes,
            esta_activo=True,
            rol="invitado_global",
        )
        print(f"[+] Usuario listo: {usuario_estudiantes.usuario} (rol={usuario_estudiantes.rol}, acceso global)")
    except Exception as e:
        print(f"[!] Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

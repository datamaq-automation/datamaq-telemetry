import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.use_cases.gestionar_usuarios import GestionarUsuariosUseCase
from src.domain.auth.services import HashContrasenaService
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.mysql_repositories import MySQLUsuariosRepository


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Crea (idempotentemente) el usuario administrador de Datamaq Telemetry."
    )
    parser.add_argument("--usuario", required=True, help="Nombre de usuario del administrador.")
    return parser


def obtener_contrasena(environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else dict(os.environ)
    contrasena = env.get("ADMIN_PASSWORD")
    if contrasena:
        return contrasena
    return getpass.getpass("Contraseña del administrador: ")


def main() -> None:
    parser = construir_parser()
    args = parser.parse_args()

    contrasena = obtener_contrasena()

    session_factory = get_session_factory()
    db = session_factory()
    try:
        repo = MySQLUsuariosRepository(db)
        use_case = GestionarUsuariosUseCase(repo, HashContrasenaService())
        usuario = use_case.crear_usuario(args.usuario, contrasena, esta_activo=True, rol="admin")
        print(f"[+] Usuario administrador listo: {usuario.usuario}")
    except Exception as e:
        print(f"[!] Error creando el usuario administrador: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

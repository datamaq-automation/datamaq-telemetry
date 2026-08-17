import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.use_cases.gestionar_usuarios import GestionarUsuariosUseCase
from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.ports import RepositorioUsuariosPort
from src.domain.auth.services import HashContrasenaService
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.mysql_repositories import MySQLUsuariosRepository

USUARIO_INVITADO = "invitado"
CONTRASENA_DEFAULT = "invitado"


def obtener_contrasena(environ: dict[str, str] | None = None) -> str:
    """Devuelve GUEST_PASSWORD; si no existe, advierte y cae a la contraseña por defecto."""
    env = environ if environ is not None else dict(os.environ)
    contrasena = env.get("GUEST_PASSWORD")
    if contrasena:
        return contrasena
    print(
        f"[!] ADVERTENCIA: usando la contraseña por defecto '{CONTRASENA_DEFAULT}' "
        "para el usuario invitado. Defina GUEST_PASSWORD en producción.",
        file=sys.stderr,
    )
    return CONTRASENA_DEFAULT


def crear_invitado(
    repo_usuarios: RepositorioUsuariosPort,
    hash_service: HashContrasenaService,
    contrasena: str,
) -> UsuarioAuth:
    """Crea idempotentemente el usuario invitado con rol 'invitado'."""
    use_case = GestionarUsuariosUseCase(repo_usuarios, hash_service)
    return use_case.crear_usuario(USUARIO_INVITADO, contrasena, esta_activo=True, rol="invitado")


def main() -> None:
    contrasena = obtener_contrasena()

    session_factory = get_session_factory()
    db = session_factory()
    try:
        repo = MySQLUsuariosRepository(db)
        usuario = crear_invitado(repo, HashContrasenaService(), contrasena)
        print(f"[+] Usuario invitado listo: {usuario.usuario} (rol={usuario.rol})")
    except Exception as e:
        print(f"[!] Error creando el usuario invitado: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

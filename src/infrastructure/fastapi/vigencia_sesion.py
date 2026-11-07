"""src/infrastructure/fastapi/vigencia_sesion.py — Chequeo de vigencia de una sesión ya autenticada (Issue #141).

Lo comparten `get_usuario_actual` (HTTP, en cada request) y el latido de /ws/live (cada ~25 s). Así una baja, una
revocación o un cambio de contraseña cortan también las conexiones abiertas, no solo las requests nuevas.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI

from src.domain.auth.ports import RepositorioUsuariosPort
from src.domain.auth.services import TokenRevocationService
from src.infrastructure.fastapi.acceso_oauth import integracion_oauth_vigente_ws
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.repositories.usuarios_repository import MySQLUsuariosRepository

logger = get_logger("vigencia_sesion")


def sesion_vigente(
    claims: dict[str, Any],
    repo_usuarios: RepositorioUsuariosPort | None,
    revocation: TokenRevocationService,
) -> bool:
    """True si la sesión del token sigue vigente: no revocada en memoria, cuenta activa y emitida después de la
    última revocación global persistida (cambio de contraseña o logout-todas)."""
    sub = str(claims.get("sub", ""))
    iat = int(claims.get("iat", 0))

    # Verificación de revocación de sesión por cambio de contraseña o logout en memoria
    if revocation.esta_revocado(sub, iat):
        return False

    # Verificación de revocación global persistida en base de datos (ISO 27001 A.5.15)
    if repo_usuarios is not None and sub:
        usuario = repo_usuarios.obtener_por_id(sub)
        # Una cuenta dada de baja no autentica aunque su token siga vigente (datamaq#127).
        if usuario is not None and not usuario.esta_activo:
            return False
        if usuario is not None and usuario.sesiones_revocadas_antes_de is not None:
            rev_dt = usuario.sesiones_revocadas_antes_de
            if rev_dt.tzinfo is None:
                rev_dt = rev_dt.replace(tzinfo=timezone.utc)
            token_iat = datetime.fromtimestamp(iat, tz=timezone.utc)
            if token_iat < rev_dt:
                return False
    return True


def sesion_ws_vigente(app: FastAPI, claims: dict[str, Any], revocation: TokenRevocationService) -> bool:
    """Igual que `sesion_vigente` más la vigencia del token (`exp`) y de la integración OAuth, para el latido de
    /ws/live. Abre una sesión de base de datos de vida corta y la cierra al terminar, como
    `integracion_oauth_vigente_ws`. Bloqueante: llamarla con `asyncio.to_thread`. Falla cerrada."""
    exp = claims.get("exp")
    if exp is not None and int(exp) <= int(datetime.now(timezone.utc).timestamp()):
        return False
    try:
        proveedor = app.dependency_overrides.get(get_db_session, get_db_session)
        generador = proveedor()
        try:
            vigente = sesion_vigente(claims, MySQLUsuariosRepository(next(generador)), revocation)
        finally:
            generador.close()
    except Exception as exc:
        logger.warning("ws_revalidacion_sesion_fallo", error=str(exc))
        return False
    return vigente and integracion_oauth_vigente_ws(app, claims)

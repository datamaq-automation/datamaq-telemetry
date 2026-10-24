"""src/infrastructure/fastapi/acceso_oauth.py — Chequeo compartido de vigencia de los access tokens OAuth (Issue #33).

Un access token OAuth (el JWT lleva `client_id`) vale solo mientras la integración siga conectada. Lo usan
`get_usuario_actual` (HTTP) y la autenticación de /ws/live, que valida el JWT por su cuenta.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI

from src.domain.oauth.ports import OAuthRepositoryPort
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.repositories.oauth_repository import MySQLOAuthRepository

logger = get_logger("acceso_oauth")

# El `iat` del JWT es entero (trunca hasta 1 s), MySQL DATETIME sin fracciones puede redondear `created_at`
# hasta 0,5 s hacia arriba, y el refresh se crea microsegundos antes de firmar el access. Sin margen, el
# refresh emitido junto con el access quedaría "posterior" a él y lo cortaría.
TOLERANCIA_EMISION = timedelta(seconds=2)


def integracion_oauth_vigente(claims: dict[str, Any], repo_oauth: OAuthRepositoryPort | None) -> bool:
    """True si el token no es OAuth, o si su integración sigue conectada.

    Solo cuenta un refresh sin revocar creado hasta el `iat` del access más la tolerancia: así un access token
    emitido antes de una desconexión no revive cuando el usuario reconecta el mismo cliente.
    Falla cerrada: ante cualquier error del repositorio, o claims o repositorio ausentes, devuelve False.
    """
    client_id = claims.get("client_id")
    if not client_id:
        return True
    try:
        sub = str(claims.get("sub", ""))
        if not sub or repo_oauth is None:
            return False
        emitido = datetime.fromtimestamp(int(claims["iat"]), tz=timezone.utc)
        return repo_oauth.tiene_integracion_activa(sub, str(client_id), emitido + TOLERANCIA_EMISION)
    except Exception as exc:
        logger.warning("oauth_chequeo_integracion_fallo", client_id=str(client_id), error=str(exc))
        return False


def integracion_oauth_vigente_ws(app: FastAPI, claims: dict[str, Any]) -> bool:
    """Igual que `integracion_oauth_vigente`, para /ws/live, que no pasa por `get_usuario_actual`.

    Abre una sesión de vida corta y la cierra al terminar: con `Depends` quedaría tomada toda la vida del
    WebSocket. Respeta `app.dependency_overrides[get_db_session]`, como el resto de la app. Bloqueante:
    llamarla con `asyncio.to_thread`. Falla cerrada.
    """
    if not claims.get("client_id"):
        return True
    try:
        proveedor = app.dependency_overrides.get(get_db_session, get_db_session)
        generador = proveedor()
        try:
            return integracion_oauth_vigente(claims, MySQLOAuthRepository(next(generador)))
        finally:
            generador.close()
    except Exception as exc:
        logger.warning("oauth_chequeo_integracion_ws_fallo", client_id=str(claims.get("client_id")), error=str(exc))
        return False

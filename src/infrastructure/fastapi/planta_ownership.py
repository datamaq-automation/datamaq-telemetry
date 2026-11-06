"""src/infrastructure/fastapi/planta_ownership.py."""

from typing import Annotated, Any

from fastapi import Depends, HTTPException

from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.domain.auth.services import roles_de_acceso_global
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.infrastructure.fastapi.auth_dependencies import (
    get_acceso_plantas_use_case,
    get_accesos_planta_repository,
)
from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.settings.config import get_settings
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.repositories.accesos_planta_repository import MySQLAccesosPlantaRepository
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

logger = get_logger("planta_ownership")


def resolver_planta_permitida(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    acceso_plantas: Annotated[GestionarAccesoPlantasUseCase, Depends(get_acceso_plantas_use_case)],
    planta_id: str | None = None,
) -> str | None:
    """Planta efectiva según `PoliticaAccesoPlantasService`: la pedida (path o query) si el usuario
    puede verla, o su planta activa (la misma que `planta_activa_id` de `/auth/me`) si no pidió ninguna.

    404 en vez de 403, con el mismo detalle para una planta ajena y una inexistente, para no
    confirmar la existencia del id. Sin auth (AUTH_REQUIRED=False) se resuelve como rol global.
    """
    if get_settings().AUTH_REQUIRED:
        usuario_id = str(claims.get("sub") or "") or None
        rol = str(claims.get("rol") or "")
        organizacion_id = claims.get("org")
    else:
        usuario_id, rol, organizacion_id = None, "superadmin", None
    try:
        return acceso_plantas.resolver_planta_permitida(usuario_id, rol, organizacion_id, planta_id)
    except PlantaNoEncontradaError as e:
        raise HTTPException(status_code=404, detail="planta_no_encontrada") from e


def resolver_plantas_permitidas_ws(app: Any, claims: dict[str, Any]) -> frozenset[str] | None:
    """Resuelve el conjunto de plantas permitidas para un cliente WebSocket autenticado.

    - superadmin: None (ve todas las plantas de todas las organizaciones).
    - Usuario con filas explícitas en user_facility_access: frozenset con las plantas permitidas.
    - Usuario sin filas explícitas en user_facility_access (acceso global a su org): None.
    """
    if claims.get("rol") == "superadmin":
        return None

    usuario_id = claims.get("sub")
    if not usuario_id:
        return None

    rol = claims.get("rol", "operador")
    organizacion_id = claims.get("org")

    try:
        if get_acceso_plantas_use_case in app.dependency_overrides:
            use_case = app.dependency_overrides[get_acceso_plantas_use_case]()
            repo_accesos = getattr(use_case, "repo_accesos", None)
            if repo_accesos is not None:
                accesos = repo_accesos.listar_por_usuario(usuario_id)
                if isinstance(accesos, (list, tuple, set, frozenset)) and not accesos:
                    return None
            plantas = use_case.resolver(usuario_id, rol, organizacion_id)
            if plantas is None:
                return None
            return frozenset(p.id if hasattr(p, "id") else str(p) for p in plantas)

        if get_accesos_planta_repository in app.dependency_overrides:
            repo_accesos = app.dependency_overrides[get_accesos_planta_repository]()
            accesos = repo_accesos.listar_por_usuario(usuario_id)
            if not accesos:
                return None
            repo_org = YamlOrganizacionesRepository()
            roles_globales = roles_de_acceso_global(get_settings().ROLES_ACCESO_GLOBAL_EXTRA)
            use_case = GestionarAccesoPlantasUseCase(repo_accesos, repo_org, roles_globales=roles_globales)
            plantas = use_case.resolver(usuario_id, rol, organizacion_id)
            return frozenset(p.id for p in plantas)

        proveedor = app.dependency_overrides.get(get_db_session, get_db_session)
        generador = proveedor()
        try:
            db = next(generador)
            repo_accesos = MySQLAccesosPlantaRepository(db)
            accesos = repo_accesos.listar_por_usuario(usuario_id)
            if not accesos:
                return None
            repo_org = YamlOrganizacionesRepository()
            roles_globales = roles_de_acceso_global(get_settings().ROLES_ACCESO_GLOBAL_EXTRA)
            use_case = GestionarAccesoPlantasUseCase(repo_accesos, repo_org, roles_globales=roles_globales)
            plantas = use_case.resolver(usuario_id, rol, organizacion_id)
            return frozenset(p.id for p in plantas)
        finally:
            generador.close()
    except Exception as exc:
        logger.warning("ws_resolver_plantas_fallido", usuario_id=str(usuario_id), error=str(exc))
        return None

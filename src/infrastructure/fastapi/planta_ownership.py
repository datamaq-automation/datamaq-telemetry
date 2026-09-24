"""src/infrastructure/fastapi/planta_ownership.py."""

from typing import Annotated, Any

from fastapi import Depends, HTTPException

from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.settings.config import get_settings


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

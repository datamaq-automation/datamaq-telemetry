from typing import Annotated, Any

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from src.domain.telemetria.services import debe_recibir_evento
from src.domain.telemetria.value_objects import MacAddress
from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.settings.config import get_settings
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.mysql_repositories import (
    MySQLDispositivosRepository,
    MySQLGruposDispositivosRepository,
    MySQLOrganizacionesRepository,
)


def verificar_propiedad_dispositivo(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    db: Annotated[Session, Depends(get_db_session)],
    device_id: str | None = None,
    dispositivo_id: str | None = None,
) -> None:
    """Rechaza con 404 si el dispositivo pedido (UUID o MAC) no pertenece a la organización
    del usuario autenticado. Superadmin y modo sin auth (AUTH_REQUIRED=False) pasan sin chequeo.

    404 en vez de 403 para no confirmar la existencia del dispositivo a un usuario ajeno.
    """
    settings = get_settings()
    if not settings.AUTH_REQUIRED or claims.get("rol") in ("superadmin", "invitado_global"):
        return

    id_dispositivo = device_id or dispositivo_id
    if id_dispositivo is None:
        return

    repo_dispositivos = MySQLDispositivosRepository(db)
    dispositivo = repo_dispositivos.obtener_por_id(id_dispositivo)
    if dispositivo is None:
        try:
            dispositivo = repo_dispositivos.obtener_por_uid(MacAddress(id_dispositivo))
        except Exception:
            dispositivo = None
    if dispositivo is None:
        raise HTTPException(status_code=404, detail="dispositivo_no_encontrado")

    organizacion_dispositivo = None
    if dispositivo.planta_id:
        repo_organizaciones = MySQLOrganizacionesRepository(db)
        planta = repo_organizaciones.obtener_planta_por_id(dispositivo.planta_id)
        organizacion_dispositivo = planta.organizacion_id if planta else None

    if not debe_recibir_evento(False, claims.get("org"), organizacion_dispositivo):
        raise HTTPException(status_code=404, detail="dispositivo_no_encontrado")


def verificar_propiedad_grupo_dispositivos(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    db: Annotated[Session, Depends(get_db_session)],
    grupo_id: str | None = None,
) -> None:
    """Rechaza con 404 si el grupo de dispositivos pedido no pertenece a la organización
    del usuario autenticado. Superadmin y modo sin auth (AUTH_REQUIRED=False) pasan sin chequeo.
    """
    settings = get_settings()
    if not settings.AUTH_REQUIRED or claims.get("rol") in ("superadmin", "invitado_global"):
        return

    if grupo_id is None:
        return

    repo_grupos = MySQLGruposDispositivosRepository(db)
    grupo = repo_grupos.obtener_por_id(grupo_id)
    if grupo is None:
        raise HTTPException(status_code=404, detail="grupo_no_encontrado")

    repo_organizaciones = MySQLOrganizacionesRepository(db)
    planta = repo_organizaciones.obtener_planta_por_id(grupo.planta_id)
    organizacion_grupo = planta.organizacion_id if planta else None

    if not debe_recibir_evento(False, claims.get("org"), organizacion_grupo):
        raise HTTPException(status_code=404, detail="grupo_no_encontrado")

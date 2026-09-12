"""src/infrastructure/fastapi/device_ownership.py."""

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
    MySQLEventosDisponibilidadRepository,
    MySQLGruposDispositivosRepository,
    MySQLMaquinasRepository,
    MySQLOrganizacionesRepository,
)
from src.infrastructure.yaml.repositories.organizaciones_repository import (
    YamlOrganizacionesRepository,
)


def _resolver_organizacion_planta(planta_id: str | None, db: Session) -> str | None:
    """Resuelve el ID de organización asociado a una planta.

    Prioriza el modelo declarativo YAML (fuente de verdad ISA-95/GitOps) y realiza
    fallback a la base de datos relacional MySQL para entornos de prueba, seeds o
    dispositivos provisionados dinámicamente.
    """
    if not planta_id:
        return None
    repo_yaml = YamlOrganizacionesRepository()
    planta = repo_yaml.obtener_planta_por_id(planta_id)
    if planta:
        return planta.organizacion_id
    repo_sql = MySQLOrganizacionesRepository(db)
    planta_sql = repo_sql.obtener_planta_por_id(planta_id)
    return planta_sql.organizacion_id if planta_sql else None


def _organizacion_de_dispositivo(db: Session, dispositivo_id: str | None) -> str | None:
    """Resuelve dispositivo_id -> planta_id -> organizacion_id. None si no se puede resolver."""
    if dispositivo_id is None:
        return None
    repo_dispositivos = MySQLDispositivosRepository(db)
    dispositivo = repo_dispositivos.obtener_por_id(dispositivo_id)
    if dispositivo is None or not dispositivo.planta_id:
        return None
    return _resolver_organizacion_planta(dispositivo.planta_id, db)


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

    organizacion_dispositivo = _resolver_organizacion_planta(dispositivo.planta_id, db)

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

    organizacion_grupo = _resolver_organizacion_planta(grupo.planta_id, db)

    if not debe_recibir_evento(False, claims.get("org"), organizacion_grupo):
        raise HTTPException(status_code=404, detail="grupo_no_encontrado")


def verificar_propiedad_maquina(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    db: Annotated[Session, Depends(get_db_session)],
    maquina_id: str | None = None,
) -> None:
    """Rechaza con 404 si la máquina pedida no pertenece a la organización del usuario
    autenticado. Superadmin y modo sin auth (AUTH_REQUIRED=False) pasan sin chequeo.
    """
    settings = get_settings()
    if not settings.AUTH_REQUIRED or claims.get("rol") in ("superadmin", "invitado_global"):
        return

    if maquina_id is None:
        return

    repo_maquinas = MySQLMaquinasRepository(db)
    maquina = repo_maquinas.obtener_por_id(maquina_id)
    if maquina is None:
        raise HTTPException(status_code=404, detail="maquina_no_encontrada")

    organizacion_maquina = _organizacion_de_dispositivo(db, maquina.dispositivo_id)
    if not debe_recibir_evento(False, claims.get("org"), organizacion_maquina):
        raise HTTPException(status_code=404, detail="maquina_no_encontrada")


def verificar_propiedad_evento_disponibilidad(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    db: Annotated[Session, Depends(get_db_session)],
    evento_id: int | None = None,
) -> None:
    """Rechaza con 404 si el evento de disponibilidad pedido no pertenece a la organización
    del usuario autenticado. Superadmin y modo sin auth (AUTH_REQUIRED=False) pasan sin chequeo.
    """
    settings = get_settings()
    if not settings.AUTH_REQUIRED or claims.get("rol") in ("superadmin", "invitado_global"):
        return

    if evento_id is None:
        return

    repo_eventos = MySQLEventosDisponibilidadRepository(db)
    evento = repo_eventos.obtener_por_id(evento_id)
    if evento is None:
        raise HTTPException(status_code=404, detail="evento_no_encontrado")

    repo_maquinas = MySQLMaquinasRepository(db)
    maquina = repo_maquinas.obtener_por_id(evento.maquina_id)
    if maquina is None:
        raise HTTPException(status_code=404, detail="evento_no_encontrado")

    organizacion_evento = _organizacion_de_dispositivo(db, maquina.dispositivo_id)
    if not debe_recibir_evento(False, claims.get("org"), organizacion_evento):
        raise HTTPException(status_code=404, detail="evento_no_encontrado")

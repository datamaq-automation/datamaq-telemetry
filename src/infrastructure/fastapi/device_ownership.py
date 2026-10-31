"""src/infrastructure/fastapi/device_ownership.py."""

from typing import Annotated, Any

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.domain.telemetria.services import debe_recibir_evento
from src.domain.telemetria.value_objects import MacAddress
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import get_usuario_actual, repo_dispositivos_resuelto
from src.infrastructure.settings.config import get_settings
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.mysql_repositories import (
    MySQLEventosDisponibilidadRepository,
    MySQLMaquinasRepository,
    MySQLTelemetriaRepository,
)
from src.infrastructure.yaml.repositories.organizaciones_repository import (
    YamlOrganizacionesRepository,
)


def _resolver_organizacion_planta(planta_id: str | None) -> str | None:
    """Resuelve el ID de organización de una planta contra el YAML, única fuente de estructura.

    Una planta que no está declarada en `data/organizaciones.yml` no existe: el
    dispositivo queda sin organización y la verificación de propiedad lo rechaza.
    """
    if not planta_id:
        return None
    planta = YamlOrganizacionesRepository().obtener_planta_por_id(planta_id)
    return planta.organizacion_id if planta else None


def _organizacion_de_dispositivo(db: Session, dispositivo_id: str | None) -> str | None:
    """Resuelve dispositivo_id -> planta_id -> organizacion_id. None si no se puede resolver."""
    if dispositivo_id is None:
        return None
    repo_dispositivos = repo_dispositivos_resuelto(db)
    dispositivo = repo_dispositivos.obtener_por_id(dispositivo_id)
    if dispositivo is None or not dispositivo.planta_id:
        return None
    return _resolver_organizacion_planta(dispositivo.planta_id)


def verificar_propiedad_dispositivo(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    db: Annotated[Session, Depends(get_db_session)],
    acceso_plantas: Annotated[GestionarAccesoPlantasUseCase | None, Depends(get_acceso_plantas_use_case)] = None,
    device_id: str | None = None,
    dispositivo_id: str | None = None,
) -> None:
    """Rechaza con 404 si el dispositivo pedido (UUID o MAC) no pertenece a la organización
    o planta asignada del usuario autenticado. Superadmin y modo sin auth pasan sin chequeo.

    404 en vez de 403 para no confirmar la existencia del dispositivo a un usuario ajeno.
    """
    settings = get_settings()
    if not settings.AUTH_REQUIRED or claims.get("rol") == "superadmin":
        return

    id_dispositivo = device_id or dispositivo_id
    if id_dispositivo is None:
        return

    repo_dispositivos = repo_dispositivos_resuelto(db)
    dispositivo = repo_dispositivos.obtener_por_id(id_dispositivo)
    if dispositivo is None:
        try:
            dispositivo = repo_dispositivos.obtener_por_uid(MacAddress(id_dispositivo))
        except Exception:
            dispositivo = None
    if dispositivo is None:
        raise HTTPException(status_code=404, detail="dispositivo_no_encontrado")

    organizacion_dispositivo = _resolver_organizacion_planta(dispositivo.planta_id)

    if not debe_recibir_evento(False, claims.get("org"), organizacion_dispositivo):
        raise HTTPException(status_code=404, detail="dispositivo_no_encontrado")

    if acceso_plantas is not None and dispositivo.planta_id:
        try:
            acceso_plantas.resolver_planta_permitida(
                usuario_id=str(claims.get("sub") or "") or None,
                rol=str(claims.get("rol") or ""),
                organizacion_id=claims.get("org"),
                planta_id=dispositivo.planta_id,
            )
        except PlantaNoEncontradaError as err:
            raise HTTPException(status_code=404, detail="dispositivo_no_encontrado") from err


class VerificadorPropiedadDispositivo:
    """Verificación de propiedad de dispositivo para llamadas imperativas desde un router.

    Aplica el mismo chequeo que el Depends de router de `verificar_propiedad_dispositivo`, incluida la
    asignación por planta (user_facility_access, #110). Sin acceso_plantas solo aplica el filtro de organización.
    """

    def __init__(
        self,
        claims: dict[str, Any],
        db: Session,
        acceso_plantas: GestionarAccesoPlantasUseCase | None = None,
    ) -> None:
        self._claims = claims
        self._db = db
        self._acceso_plantas = acceso_plantas

    def exigir(self, dispositivo_id: str | None) -> None:
        verificar_propiedad_dispositivo(
            claims=self._claims,
            db=self._db,
            acceso_plantas=self._acceso_plantas,
            dispositivo_id=dispositivo_id,
        )

    def pertenece(self, dispositivo_id: str | None) -> bool:
        try:
            self.exigir(dispositivo_id)
        except HTTPException:
            return False
        return True


def get_verificador_propiedad_dispositivo(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    db: Annotated[Session, Depends(get_db_session)],
    acceso_plantas: Annotated[GestionarAccesoPlantasUseCase, Depends(get_acceso_plantas_use_case)],
) -> VerificadorPropiedadDispositivo:
    return VerificadorPropiedadDispositivo(claims, db, acceso_plantas)


def verificar_propiedad_maquina(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    db: Annotated[Session, Depends(get_db_session)],
    maquina_id: str | None = None,
) -> None:
    """Rechaza con 404 si la máquina pedida no pertenece a la organización del usuario
    autenticado. Superadmin y modo sin auth (AUTH_REQUIRED=False) pasan sin chequeo.
    """
    settings = get_settings()
    if not settings.AUTH_REQUIRED or claims.get("rol") == "superadmin":
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


def verificar_propiedad_alerta(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    db: Annotated[Session, Depends(get_db_session)],
    alerta_id: int | None = None,
) -> None:
    """Rechaza con 404 si la alerta pedida no pertenece a la organización del usuario
    autenticado (alerta -> dispositivo -> planta -> organización). Superadmin,
    y modo sin auth (AUTH_REQUIRED=False) pasan sin chequeo.
    """
    settings = get_settings()
    if not settings.AUTH_REQUIRED or claims.get("rol") == "superadmin":
        return

    if alerta_id is None:
        return

    alerta = MySQLTelemetriaRepository(db).obtener_alerta_por_id(alerta_id)
    if alerta is None:
        raise HTTPException(status_code=404, detail="alerta_no_encontrada")

    organizacion_alerta = _organizacion_de_dispositivo(db, alerta.dispositivo_id)
    if not debe_recibir_evento(False, claims.get("org"), organizacion_alerta):
        raise HTTPException(status_code=404, detail="alerta_no_encontrada")


def verificar_propiedad_evento_disponibilidad(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    db: Annotated[Session, Depends(get_db_session)],
    evento_id: int | None = None,
) -> None:
    """Rechaza con 404 si el evento de disponibilidad pedido no pertenece a la organización
    del usuario autenticado. Superadmin y modo sin auth (AUTH_REQUIRED=False) pasan sin chequeo.
    """
    settings = get_settings()
    if not settings.AUTH_REQUIRED or claims.get("rol") == "superadmin":
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

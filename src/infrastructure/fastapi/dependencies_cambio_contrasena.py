"""src/infrastructure/fastapi/dependencies_cambio_contrasena.py.

Dependencias FastAPI del cambio de contraseña autenticado.

Viven fuera de dependencies.py para no superar el límite de tamaño de archivo de ese módulo.
"""

from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from src.application.use_cases.cambio_contrasena import (
    ConfirmarCambioContrasenaUseCase,
    SolicitarCambioContrasenaUseCase,
)
from src.domain.auth.ports import RepositorioCambioContrasenaPort, RepositorioUsuariosPort, ServicioEmailPort
from src.domain.auth.services import HashContrasenaService
from src.infrastructure.fastapi.dependencies import get_email_service, get_settings_dep, get_usuarios_repository
from src.infrastructure.settings.config import Settings
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.repositories.cambio_contrasena_repository import (
    MySQLCambioContrasenaRepository,
)

logger = get_logger("cambio_contrasena")


def get_clave_otp(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> str:
    """Clave HMAC de los OTP. Sin clave usable (producción sin OTP_HMAC_KEY) el cambio responde 503."""
    if not settings.otp_hmac_configurada:
        # El código es contrato con app-datamaq: no lleva sufijo. El nombre de la variable va solo al log.
        logger.error("cambio_contrasena_sin_otp_hmac_key", variable="OTP_HMAC_KEY")
        raise HTTPException(status_code=503, detail="cambio_contrasena_no_disponible")
    return settings.OTP_HMAC_KEY


def get_cambio_contrasena_repository(
    db: Annotated[Session, Depends(get_db_session)],
) -> RepositorioCambioContrasenaPort:
    return MySQLCambioContrasenaRepository(db)


def get_solicitar_cambio_contrasena_use_case(
    usuarios_repo: Annotated[RepositorioUsuariosPort, Depends(get_usuarios_repository)],
    repo: Annotated[RepositorioCambioContrasenaPort, Depends(get_cambio_contrasena_repository)],
    email_service: Annotated[ServicioEmailPort, Depends(get_email_service)],
    clave_otp: Annotated[str, Depends(get_clave_otp)],
) -> SolicitarCambioContrasenaUseCase:
    return SolicitarCambioContrasenaUseCase(
        repo=repo,
        usuarios=usuarios_repo,
        hash_service=HashContrasenaService,
        email=email_service,
        clave_otp=clave_otp,
    )


def get_confirmar_cambio_contrasena_use_case(
    usuarios_repo: Annotated[RepositorioUsuariosPort, Depends(get_usuarios_repository)],
    repo: Annotated[RepositorioCambioContrasenaPort, Depends(get_cambio_contrasena_repository)],
    email_service: Annotated[ServicioEmailPort, Depends(get_email_service)],
    clave_otp: Annotated[str, Depends(get_clave_otp)],
) -> ConfirmarCambioContrasenaUseCase:
    return ConfirmarCambioContrasenaUseCase(
        repo=repo,
        usuarios=usuarios_repo,
        hash_service=HashContrasenaService,
        email=email_service,
        clave_otp=clave_otp,
    )

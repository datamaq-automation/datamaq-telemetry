from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.application.use_cases.gestionar_2fa import (
    Activar2FAUseCase,
    Desactivar2FAUseCase,
    Setup2FAUseCase,
    Verificar2FAUseCase,
)
from src.application.use_cases.gestionar_dispositivos_confiables import (
    RevocarDispositivosConfiablesUseCase,
)
from src.domain.auth.ports import (
    CifradorSecreto2FAPort,
    RepositorioDispositivosConfiablesPort,
    RepositorioUsuariosPort,
    ServicioTOTPPort,
)
from src.domain.auth.services import HashContrasenaService
from src.infrastructure.auth.cifrador_2fa import CifradorSecreto2FA
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.auth.totp_service import PyOtpService
from src.infrastructure.fastapi.dependencies import get_rate_limiter
from src.infrastructure.settings.config import get_settings
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.mysql_repositories import (
    MySQLDispositivosConfiablesRepository,
    MySQLUsuariosRepository,
)


def get_usuarios_repository(
    db: Annotated[Session, Depends(get_db_session)],
) -> RepositorioUsuariosPort:
    return MySQLUsuariosRepository(db)


def get_dispositivos_confiables_repository(
    db: Annotated[Session, Depends(get_db_session)],
) -> RepositorioDispositivosConfiablesPort:
    return MySQLDispositivosConfiablesRepository(db)


def get_auth_use_case(
    repo_usuarios: Annotated[RepositorioUsuariosPort, Depends(get_usuarios_repository)],
    repo_dispositivos: Annotated[
        RepositorioDispositivosConfiablesPort, Depends(get_dispositivos_confiables_repository)
    ],
) -> AutenticarUsuarioUseCase:
    settings = get_settings()
    rate_limiter = get_rate_limiter()
    return AutenticarUsuarioUseCase(
        repo_usuarios=repo_usuarios,
        hash_service=HashContrasenaService(),
        token_service=JwtTokenService(settings.API_SECRET_KEY),
        minutos_validez=settings.AUTH_TOKEN_EXPIRA_MINUTOS,
        rate_limiter=rate_limiter,
        guest_organizacion_id=settings.GUEST_ORGANIZATION_ID,
        repo_dispositivos=repo_dispositivos,
    )


def get_totp_service() -> ServicioTOTPPort:
    return PyOtpService()


def get_cifrador_2fa() -> CifradorSecreto2FAPort:
    settings = get_settings()
    return CifradorSecreto2FA(settings.API_SECRET_KEY)


def get_verificar_2fa_use_case(
    db: Annotated[Session, Depends(get_db_session)],
    totp_service: Annotated[ServicioTOTPPort, Depends(get_totp_service)],
    cifrador_service: Annotated[CifradorSecreto2FAPort, Depends(get_cifrador_2fa)],
    repo_dispositivos: Annotated[
        RepositorioDispositivosConfiablesPort, Depends(get_dispositivos_confiables_repository)
    ],
) -> Verificar2FAUseCase:
    repo_usuarios = MySQLUsuariosRepository(db)
    settings = get_settings()
    rate_limiter = get_rate_limiter()
    return Verificar2FAUseCase(
        repo_usuarios=repo_usuarios,
        token_service=JwtTokenService(settings.API_SECRET_KEY),
        totp_service=totp_service,
        cifrador_service=cifrador_service,
        minutos_validez=settings.AUTH_TOKEN_EXPIRA_MINUTOS,
        rate_limiter=rate_limiter,
        repo_dispositivos=repo_dispositivos,
    )


def get_revocar_dispositivos_use_case(
    repo_dispositivos: Annotated[
        RepositorioDispositivosConfiablesPort, Depends(get_dispositivos_confiables_repository)
    ],
) -> RevocarDispositivosConfiablesUseCase:
    return RevocarDispositivosConfiablesUseCase(repo_dispositivos)


def get_setup_2fa_use_case(
    db: Annotated[Session, Depends(get_db_session)],
    totp_service: Annotated[ServicioTOTPPort, Depends(get_totp_service)],
) -> Setup2FAUseCase:
    return Setup2FAUseCase(
        repo_usuarios=MySQLUsuariosRepository(db),
        totp_service=totp_service,
    )


def get_activar_2fa_use_case(
    db: Annotated[Session, Depends(get_db_session)],
    totp_service: Annotated[ServicioTOTPPort, Depends(get_totp_service)],
    cifrador_service: Annotated[CifradorSecreto2FAPort, Depends(get_cifrador_2fa)],
) -> Activar2FAUseCase:
    return Activar2FAUseCase(
        repo_usuarios=MySQLUsuariosRepository(db),
        totp_service=totp_service,
        cifrador_service=cifrador_service,
    )


def get_desactivar_2fa_use_case(
    db: Annotated[Session, Depends(get_db_session)],
    totp_service: Annotated[ServicioTOTPPort, Depends(get_totp_service)],
    cifrador_service: Annotated[CifradorSecreto2FAPort, Depends(get_cifrador_2fa)],
) -> Desactivar2FAUseCase:
    return Desactivar2FAUseCase(
        repo_usuarios=MySQLUsuariosRepository(db),
        hash_service=HashContrasenaService(),
        totp_service=totp_service,
        cifrador_service=cifrador_service,
    )

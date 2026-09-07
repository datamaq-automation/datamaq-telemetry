from typing import Literal

from pydantic import BaseModel, Field

from src.application.dtos.tipos import FechaHoraUTC


class LoginRequestDTO(BaseModel):
    usuario: str = Field(min_length=1, max_length=128)
    contrasena: str = Field(min_length=1, max_length=128)


class LoginResponseDTO(BaseModel):
    token: str | None = None
    expira_en: FechaHoraUTC
    require_2fa: bool = False
    mfa_token: str | None = None


class MeResponseDTO(BaseModel):
    usuario: str
    rol: Literal["superadmin", "admin", "operador", "invitado"]
    totp_enabled: bool = False


class Verificar2FARequestDTO(BaseModel):
    mfa_token: str = Field(min_length=1)
    codigo: str = Field(min_length=1, max_length=32)


class Setup2FAResponseDTO(BaseModel):
    secret: str
    uri: str
    qr_svg: str
    backup_codes: list[str]


class Activar2FARequestDTO(BaseModel):
    secret: str = Field(min_length=16, max_length=64)
    codigo: str = Field(min_length=6, max_length=16)
    backup_codes: list[str] = Field(min_length=1)


class Desactivar2FARequestDTO(BaseModel):
    contrasena: str = Field(min_length=1, max_length=128)
    codigo: str = Field(min_length=6, max_length=32)


class Operacion2FAResponseDTO(BaseModel):
    exito: bool = True
    mensaje: str = "Operación exitosa"


class SolicitarRecuperacionDTO(BaseModel):
    usuario: str = Field(min_length=1, max_length=128)


class RestablecerContrasenaDTO(BaseModel):
    token: str = Field(min_length=1)
    nueva_contrasena: str = Field(min_length=1, max_length=128)

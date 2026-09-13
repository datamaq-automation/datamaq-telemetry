"""src/application/dtos/auth_dto.py."""

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
    device_trust_token: str | None = Field(default=None, exclude=True)


class PlantaAccesoDTO(BaseModel):
    """Planta visible para el usuario autenticado y si puede cambiar la activa (R-02)."""

    id: str
    nombre: str
    organizacion_id: str
    puede_cambiar: bool


class AsignarPlantaRequestDTO(BaseModel):
    planta_id: str = Field(min_length=1, max_length=36)
    puede_cambiar: bool = False


class AsignarPlantasRequestDTO(BaseModel):
    """Reemplaza el conjunto completo de plantas asignadas a un usuario.

    Lista vacía = volver al comportamiento por defecto (todas las plantas de su
    organización, con permiso de cambio).
    """

    plantas: list[AsignarPlantaRequestDTO] = Field(default_factory=list, max_length=100)


class MeResponseDTO(BaseModel):
    usuario: str
    rol: Literal[
        "superadmin",
        "admin",
        "operador",
        "invitado",
        "invitado_global",
        "mantenimiento",
        "ingeniero",
        "auditor",
    ]
    totp_enabled: bool = False
    organizacion_id: str | None = None
    organizacion_nombre: str | None = None
    plantas: list[PlantaAccesoDTO] = Field(default_factory=list)
    planta_activa_id: str | None = None


class Verificar2FARequestDTO(BaseModel):
    mfa_token: str = Field(min_length=1)
    codigo: str = Field(min_length=1, max_length=32)
    recordar_dispositivo: bool = False


class RevocarDispositivosResponseDTO(BaseModel):
    mensaje: str = "Dispositivos confiables revocados exitosamente"
    cantidad_revocados: int = 0


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

"""DTOs para cambio de contraseña autenticado."""

from pydantic import BaseModel, Field


class RequestPasswordChangeCodeRequest(BaseModel):
    """Body para solicitar código OTP."""

    password_actual: str = Field(..., description="Contraseña actual para validar")


class RequestPasswordChangeCodeResponse(BaseModel):
    """Response después de solicitar código."""

    status: str = Field(default="codigo_enviado", description="Estado de la solicitud")
    email_destino: str = Field(..., description="Email ofuscado donde se envió código")


class ConfirmPasswordChangeRequest(BaseModel):
    """Body para confirmar cambio de contraseña."""

    codigo: str = Field(..., min_length=4, max_length=4, description="Código OTP de 4 dígitos")
    password_nueva: str = Field(..., description="Nueva contraseña")
    password_nueva_confirm: str = Field(..., description="Confirmación de nueva contraseña")


class ConfirmPasswordChangeResponse(BaseModel):
    """Response después de confirmar cambio."""

    status: str = Field(default="cambio_exitoso", description="Estado del cambio")
    mensaje: str = Field(default="Contraseña actualizada exitosamente", description="Mensaje de éxito")

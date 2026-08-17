from datetime import datetime

from pydantic import BaseModel


class LoginRequestDTO(BaseModel):
    usuario: str
    contrasena: str


class LoginResponseDTO(BaseModel):
    token: str
    expira_en: datetime

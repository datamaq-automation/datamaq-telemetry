from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequestDTO(BaseModel):
    usuario: str = Field(min_length=1, max_length=128)
    contrasena: str = Field(min_length=1, max_length=128)


class LoginResponseDTO(BaseModel):
    token: str
    expira_en: datetime

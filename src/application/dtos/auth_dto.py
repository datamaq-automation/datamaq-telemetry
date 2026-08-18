from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LoginRequestDTO(BaseModel):
    usuario: str = Field(min_length=1, max_length=128)
    contrasena: str = Field(min_length=1, max_length=128)


class LoginResponseDTO(BaseModel):
    token: str
    expira_en: datetime


class MeResponseDTO(BaseModel):
    usuario: str
    rol: Literal["admin", "operador", "invitado"]

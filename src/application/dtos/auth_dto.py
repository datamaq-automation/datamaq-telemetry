from typing import Literal

from pydantic import BaseModel, Field

from src.application.dtos.tipos import FechaHoraUTC


class LoginRequestDTO(BaseModel):
    usuario: str = Field(min_length=1, max_length=128)
    contrasena: str = Field(min_length=1, max_length=128)


class LoginResponseDTO(BaseModel):
    token: str
    expira_en: FechaHoraUTC


class MeResponseDTO(BaseModel):
    usuario: str
    rol: Literal["admin", "operador", "invitado"]

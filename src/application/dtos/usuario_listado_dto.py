"""src/application/dtos/usuario_listado_dto.py — Fila del listado de cuentas (solo lectura, sin secretos)."""

from pydantic import BaseModel, ConfigDict


class UsuarioListadoDTO(BaseModel):
    id: str
    usuario: str
    rol: str
    organizacion_id: str | None
    esta_activo: bool
    model_config = ConfigDict(from_attributes=True)

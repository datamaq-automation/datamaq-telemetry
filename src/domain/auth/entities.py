from dataclasses import dataclass, field
from datetime import datetime, timezone


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class UsuarioAuth:
    id: str
    usuario: str
    hash_contrasena: str
    esta_activo: bool = True
    rol: str = "operador"
    creado_en: datetime = field(default_factory=ahora_utc)
    actualizado_en: datetime = field(default_factory=ahora_utc)

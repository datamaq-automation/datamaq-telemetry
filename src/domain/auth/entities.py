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
    organizacion_id: str | None = None
    totp_secret: str | None = None
    totp_enabled: bool = False
    totp_backup_codes: list[str] | None = None
    creado_en: datetime = field(default_factory=ahora_utc)
    actualizado_en: datetime = field(default_factory=ahora_utc)

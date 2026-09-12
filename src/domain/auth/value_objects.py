"""src/domain/auth/value_objects.py."""

import re
from dataclasses import dataclass

from src.domain.auth.exceptions import NombreUsuarioInvalidoError

_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


@dataclass(frozen=True)
class NombreUsuario:
    valor: str

    def __post_init__(self):
        limpio = self.valor.strip().lower()
        if not limpio:
            raise NombreUsuarioInvalidoError("El nombre de usuario no puede estar vacío.")
        if not _EMAIL_REGEX.match(limpio):
            raise NombreUsuarioInvalidoError("El nombre de usuario debe ser un correo electrónico válido.")
        object.__setattr__(self, "valor", limpio)

from dataclasses import dataclass

from src.domain.auth.exceptions import NombreUsuarioInvalidoError


@dataclass(frozen=True)
class NombreUsuario:
    valor: str

    def __post_init__(self):
        limpio = self.valor.strip().lower()
        if not limpio:
            raise NombreUsuarioInvalidoError("El nombre de usuario no puede estar vacío.")
        object.__setattr__(self, "valor", limpio)

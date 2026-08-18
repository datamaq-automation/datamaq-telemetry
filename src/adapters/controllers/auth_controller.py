from typing import Any

from src.application.dtos.auth_dto import LoginRequestDTO, LoginResponseDTO, MeResponseDTO
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.domain.auth.exceptions import CredencialesInvalidasError

ROLES_VALIDOS = frozenset({"admin", "operador", "invitado"})


class AuthController:
    def __init__(self, use_case: AutenticarUsuarioUseCase):
        self.use_case = use_case

    def login(self, dto: LoginRequestDTO) -> LoginResponseDTO:
        return self.use_case.login(dto)

    def guest(self, clave_limite: str) -> LoginResponseDTO:
        return self.use_case.guest(clave_limite)

    def me(self, claims: dict[str, Any]) -> MeResponseDTO:
        rol = claims.get("rol")
        if rol not in ROLES_VALIDOS:
            raise CredencialesInvalidasError("Rol inválido en los claims del token.")
        usuario = str(claims.get("usuario") or claims.get("sub") or "anon")
        return MeResponseDTO(usuario=usuario, rol=rol)

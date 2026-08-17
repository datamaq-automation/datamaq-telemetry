from src.application.dtos.auth_dto import LoginRequestDTO, LoginResponseDTO
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase


class AuthController:
    def __init__(self, use_case: AutenticarUsuarioUseCase):
        self.use_case = use_case

    def login(self, dto: LoginRequestDTO) -> LoginResponseDTO:
        return self.use_case.login(dto)

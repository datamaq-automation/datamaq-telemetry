from src.application.dtos.auth_dto import LoginRequestDTO, LoginResponseDTO
from src.domain.auth.entities import ahora_utc
from src.domain.auth.exceptions import CredencialesInvalidasError, UsuarioInactivoError
from src.domain.auth.ports import GeneradorTokenPort, RepositorioUsuariosPort
from src.domain.auth.services import HashContrasenaService, PoliticaExpiracionService
from src.domain.auth.value_objects import NombreUsuario


class AutenticarUsuarioUseCase:
    def __init__(
        self,
        repo_usuarios: RepositorioUsuariosPort,
        hash_service: HashContrasenaService,
        token_service: GeneradorTokenPort,
        minutos_validez: int,
    ):
        self.repo_usuarios = repo_usuarios
        self.hash_service = hash_service
        self.token_service = token_service
        self.minutos_validez = minutos_validez

    def login(self, dto: LoginRequestDTO) -> LoginResponseDTO:
        nombre = NombreUsuario(dto.usuario).valor
        usuario = self.repo_usuarios.obtener_por_usuario(nombre)
        if usuario is None:
            raise CredencialesInvalidasError("Credenciales inválidas.")
        if not self.hash_service.verificar(dto.contrasena, usuario.hash_contrasena):
            raise CredencialesInvalidasError("Credenciales inválidas.")
        if not usuario.esta_activo:
            raise UsuarioInactivoError("El usuario se encuentra inactivo.")

        expira_en = PoliticaExpiracionService.calcular_expiracion(ahora_utc(), self.minutos_validez)
        token = self.token_service.generar(usuario.id, usuario.usuario, expira_en)
        return LoginResponseDTO(token=token, expira_en=expira_en)

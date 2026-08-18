from src.application.dtos.auth_dto import LoginRequestDTO, LoginResponseDTO
from src.domain.auth.entities import ahora_utc
from src.domain.auth.exceptions import CredencialesInvalidasError, DemasiadosIntentosError, UsuarioInactivoError
from src.domain.auth.ports import GeneradorTokenPort, RepositorioUsuariosPort
from src.domain.auth.services import HashContrasenaService, PoliticaExpiracionService, RateLimiterService
from src.domain.auth.value_objects import NombreUsuario


class AutenticarUsuarioUseCase:
    def __init__(
        self,
        repo_usuarios: RepositorioUsuariosPort,
        hash_service: HashContrasenaService,
        token_service: GeneradorTokenPort,
        minutos_validez: int,
        rate_limiter: RateLimiterService | None = None,
    ):
        self.repo_usuarios = repo_usuarios
        self.hash_service = hash_service
        self.token_service = token_service
        self.minutos_validez = minutos_validez
        self.rate_limiter = rate_limiter

    def _registrar_intento(self, nombre: str) -> None:
        if self.rate_limiter is not None:
            self.rate_limiter.registrar_intento(nombre)

    def login(self, dto: LoginRequestDTO) -> LoginResponseDTO:
        nombre = NombreUsuario(dto.usuario).valor
        if self.rate_limiter is not None and not self.rate_limiter.permitir(nombre):
            raise DemasiadosIntentosError("Demasiados intentos de inicio de sesión. Intente más tarde.", usuario=nombre)
        usuario = self.repo_usuarios.obtener_por_usuario(nombre)
        if usuario is None:
            self._registrar_intento(nombre)
            raise CredencialesInvalidasError("Credenciales inválidas.", usuario=nombre)
        if not self.hash_service.verificar(dto.contrasena, usuario.hash_contrasena):
            self._registrar_intento(nombre)
            raise CredencialesInvalidasError("Credenciales inválidas.", usuario=nombre)
        if not usuario.esta_activo:
            raise UsuarioInactivoError("El usuario se encuentra inactivo.", usuario=nombre)

        if self.rate_limiter is not None:
            self.rate_limiter.resetear(nombre)

        expira_en = PoliticaExpiracionService.calcular_expiracion(ahora_utc(), self.minutos_validez)
        token = self.token_service.generar(usuario.id, usuario.usuario, expira_en, rol=usuario.rol)
        return LoginResponseDTO(token=token, expira_en=expira_en)

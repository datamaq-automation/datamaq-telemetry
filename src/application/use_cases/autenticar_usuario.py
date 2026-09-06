from typing import Any

from src.application.dtos.auth_dto import LoginRequestDTO, LoginResponseDTO, MeResponseDTO
from src.domain.auth.entities import ahora_utc
from src.domain.auth.exceptions import CredencialesInvalidasError, DemasiadosIntentosError, UsuarioInactivoError
from src.domain.auth.ports import GeneradorTokenPort, RepositorioUsuariosPort
from src.domain.auth.services import HashContrasenaService, PoliticaExpiracionService, RateLimiterService
from src.domain.auth.value_objects import NombreUsuario

ROLES_VALIDOS = frozenset({"superadmin", "admin", "operador", "invitado"})


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

    def _registrar_intento(self, clave: str) -> None:
        if self.rate_limiter is not None:
            self.rate_limiter.registrar_intento(clave)

    def login(self, dto: LoginRequestDTO, clave_limite: str | None = None) -> LoginResponseDTO:
        nombre = NombreUsuario(dto.usuario).valor
        clave = clave_limite if clave_limite is not None else nombre
        if self.rate_limiter is not None and not self.rate_limiter.permitir(clave):
            raise DemasiadosIntentosError(
                "Demasiados intentos de inicio de sesión. Intente más tarde.",
                usuario=nombre,
                retry_after_seg=self.rate_limiter.segundos_restantes(clave),
            )
        usuario = self.repo_usuarios.obtener_por_usuario(nombre)
        if usuario is None:
            self._registrar_intento(clave)
            raise CredencialesInvalidasError("Credenciales inválidas.", usuario=nombre)
        if not self.hash_service.verificar(dto.contrasena, usuario.hash_contrasena):
            self._registrar_intento(clave)
            raise CredencialesInvalidasError("Credenciales inválidas.", usuario=nombre)
        if not usuario.esta_activo:
            raise UsuarioInactivoError("El usuario se encuentra inactivo.", usuario=nombre)

        if self.rate_limiter is not None:
            self.rate_limiter.resetear(clave)

        if usuario.totp_enabled:
            expira_mfa = PoliticaExpiracionService.calcular_expiracion(ahora_utc(), 5)
            mfa_token = self.token_service.generar_mfa(usuario.id, usuario.usuario, expira_mfa)
            return LoginResponseDTO(token=None, expira_en=expira_mfa, require_2fa=True, mfa_token=mfa_token)

        expira_en = PoliticaExpiracionService.calcular_expiracion(ahora_utc(), self.minutos_validez)
        token = self.token_service.generar(usuario.id, usuario.usuario, expira_en, rol=usuario.rol)
        return LoginResponseDTO(token=token, expira_en=expira_en, require_2fa=False)

    def guest(self, clave_limite: str) -> LoginResponseDTO:
        if self.rate_limiter is not None:
            if not self.rate_limiter.permitir(clave_limite):
                raise DemasiadosIntentosError(
                    "Demasiados intentos de inicio de sesión. Intente más tarde.",
                    usuario="invitado",
                    retry_after_seg=self.rate_limiter.segundos_restantes(clave_limite),
                )
            self.rate_limiter.registrar_intento(clave_limite)

        expira_en = PoliticaExpiracionService.calcular_expiracion(ahora_utc(), self.minutos_validez)
        token = self.token_service.generar("invitado", "invitado", expira_en, rol="invitado")
        return LoginResponseDTO(token=token, expira_en=expira_en)

    def me(self, claims: dict[str, Any]) -> MeResponseDTO:
        rol = claims.get("rol")
        if rol not in ROLES_VALIDOS:
            raise CredencialesInvalidasError("Rol inválido en los claims del token.")
        usuario = str(claims.get("usuario") or claims.get("sub") or "anon")
        return MeResponseDTO(usuario=usuario, rol=rol)

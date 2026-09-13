"""src/application/use_cases/autenticar_usuario.py."""

from typing import Any

from src.application.dtos.auth_dto import LoginRequestDTO, LoginResponseDTO, MeResponseDTO
from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.domain.auth.entities import ahora_utc
from src.domain.auth.exceptions import CredencialesInvalidasError, DemasiadosIntentosError, UsuarioInactivoError
from src.domain.auth.ports import (
    GeneradorTokenPort,
    RepositorioDispositivosConfiablesPort,
    RepositorioUsuariosPort,
)
from src.domain.auth.services import (
    HashContrasenaService,
    PoliticaExpiracionService,
    RateLimiterService,
    TokenDispositivoService,
)
from src.domain.auth.value_objects import NombreUsuario

ROLES_VALIDOS = frozenset(
    {
        "superadmin",
        "admin",
        "operador",
        "invitado",
        "invitado_global",
        "mantenimiento",
        "ingeniero",
        "auditor",
    }
)


class AutenticarUsuarioUseCase:
    def __init__(
        self,
        repo_usuarios: RepositorioUsuariosPort,
        hash_service: HashContrasenaService,
        token_service: GeneradorTokenPort,
        minutos_validez: int,
        rate_limiter: RateLimiterService | None = None,
        guest_organizacion_id: str | None = None,
        repo_dispositivos: RepositorioDispositivosConfiablesPort | None = None,
        acceso_plantas: GestionarAccesoPlantasUseCase | None = None,
    ):
        self.repo_usuarios = repo_usuarios
        self.hash_service = hash_service
        self.token_service = token_service
        self.minutos_validez = minutos_validez
        self.rate_limiter = rate_limiter
        self.guest_organizacion_id = guest_organizacion_id
        self.repo_dispositivos = repo_dispositivos
        self.acceso_plantas = acceso_plantas

    def _registrar_intento(self, clave: str) -> None:
        if self.rate_limiter is not None:
            self.rate_limiter.registrar_intento(clave)

    def login(
        self,
        dto: LoginRequestDTO,
        clave_limite: str | None = None,
        clave_ip: str | None = None,
        device_token: str | None = None,
        ip_origen: str | None = None,
    ) -> LoginResponseDTO:
        nombre = NombreUsuario(dto.usuario).valor
        clave = clave_limite if clave_limite is not None else nombre

        # Mitigación de Password Spraying horizontal por IP (máx 20 intentos en 5 min)
        if clave_ip and self.rate_limiter is not None:
            k_ip = f"ip:{clave_ip}"
            if not self.rate_limiter.permitir(k_ip, max_intentos=20):
                raise DemasiadosIntentosError(
                    "Demasiados intentos fallidos desde esta dirección IP. Intente más tarde.",
                    usuario=nombre,
                    retry_after_seg=self.rate_limiter.segundos_restantes(k_ip, max_intentos=20),
                )

        if self.rate_limiter is not None and not self.rate_limiter.permitir(clave):
            raise DemasiadosIntentosError(
                "Demasiados intentos de inicio de sesión. Intente más tarde.",
                usuario=nombre,
                retry_after_seg=self.rate_limiter.segundos_restantes(clave),
            )
        usuario = self.repo_usuarios.obtener_por_usuario(nombre)
        if usuario is None:
            self._registrar_intento(clave)
            if clave_ip and self.rate_limiter is not None:
                self.rate_limiter.registrar_intento(f"ip:{clave_ip}")
            raise CredencialesInvalidasError("Credenciales inválidas.", usuario=nombre)
        if not self.hash_service.verificar(dto.contrasena, usuario.hash_contrasena):
            self._registrar_intento(clave)
            if clave_ip and self.rate_limiter is not None:
                self.rate_limiter.registrar_intento(f"ip:{clave_ip}")
            raise CredencialesInvalidasError("Credenciales inválidas.", usuario=nombre)
        if not usuario.esta_activo:
            raise UsuarioInactivoError("El usuario se encuentra inactivo.", usuario=nombre)

        if self.rate_limiter is not None:
            self.rate_limiter.resetear(clave)

        if usuario.totp_enabled:
            disp_valido = False
            if self.repo_dispositivos is not None and device_token:
                token_hash = TokenDispositivoService.calcular_hash(device_token)
                disp = self.repo_dispositivos.obtener_por_hash(token_hash)
                ahora = ahora_utc()
                if disp is not None and disp.usuario_id == usuario.id and disp.es_valido(ip_origen, ahora):
                    self.repo_dispositivos.actualizar_acceso(disp.id, ip_origen or disp.ip_origen, ahora)
                    disp_valido = True

            if not disp_valido:
                expira_mfa = PoliticaExpiracionService.calcular_expiracion(ahora_utc(), 5)
                mfa_token = self.token_service.generar_mfa(usuario.id, usuario.usuario, expira_mfa)
                return LoginResponseDTO(token=None, expira_en=expira_mfa, require_2fa=True, mfa_token=mfa_token)

        expira_en = PoliticaExpiracionService.calcular_expiracion(ahora_utc(), self.minutos_validez)
        token = self.token_service.generar(
            usuario.id, usuario.usuario, expira_en, rol=usuario.rol, organizacion_id=usuario.organizacion_id
        )
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
        token = self.token_service.generar(
            "invitado", "invitado", expira_en, rol="invitado", organizacion_id=self.guest_organizacion_id
        )
        return LoginResponseDTO(token=token, expira_en=expira_en)

    def me(self, claims: dict[str, Any]) -> MeResponseDTO:
        rol = claims.get("rol")
        if rol not in ROLES_VALIDOS:
            raise CredencialesInvalidasError("Rol inválido en los claims del token.")
        usuario = str(claims.get("usuario") or claims.get("sub") or "anon")

        # Obtener el estado real de 2FA desde el repositorio
        totp_enabled = False
        sub = str(claims.get("sub") or "")
        user = None
        if sub and sub != "anon":
            user = self.repo_usuarios.obtener_por_id(sub)
        if user is None and usuario != "anon":
            user = self.repo_usuarios.obtener_por_usuario(usuario)
        if user is not None:
            totp_enabled = bool(user.totp_enabled)

        org_id = claims.get("org") or (user.organizacion_id if user else None)
        org_nombre = None
        if user and user.organizacion_id:
            org_id = user.organizacion_id

        plantas = []
        if self.acceso_plantas is not None:
            plantas = self.acceso_plantas.resolver(user.id if user else None, str(rol), org_id)

        return MeResponseDTO(
            usuario=usuario,
            rol=rol,
            totp_enabled=totp_enabled,
            organizacion_id=org_id,
            organizacion_nombre=org_nombre,
            plantas=plantas,
            planta_activa_id=GestionarAccesoPlantasUseCase.planta_activa(plantas),
        )

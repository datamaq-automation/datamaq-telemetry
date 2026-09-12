"""src/application/use_cases/recuperar_contrasena.py."""
import hashlib
from datetime import datetime, timedelta, timezone

from src.application.dtos.auth_dto import (
    Operacion2FAResponseDTO,
    RestablecerContrasenaDTO,
    SolicitarRecuperacionDTO,
)
from src.domain.auth.exceptions import (
    ContrasenaDebilError,
    DemasiadosIntentosError,
    TokenRecuperacionInvalidoError,
)
from src.domain.auth.ports import (
    GeneradorTokenPort,
    RepositorioUsuariosPort,
    ServicioEmailPort,
)
from src.domain.auth.services import (
    HashContrasenaService,
    RateLimiterService,
    TokenRevocationService,
)
from src.domain.auth.value_objects import NombreUsuario


class SolicitarRecuperacionContrasenaUseCase:
    """Inicia el flujo de recuperación de contraseña enviando un enlace por correo."""

    def __init__(
        self,
        repositorio_usuarios: RepositorioUsuariosPort,
        generador_token: GeneradorTokenPort,
        servicio_email: ServicioEmailPort,
        frontend_url: str = "https://www.datamaq.com.ar",
        minutos_expiracion: int = 15,
        rate_limiter: RateLimiterService | None = None,
        max_solicitudes_usuario: int = 3,
        max_solicitudes_ip: int = 10,
    ):
        self.repositorio_usuarios = repositorio_usuarios
        self.generador_token = generador_token
        self.servicio_email = servicio_email
        self.frontend_url = frontend_url
        self.minutos_expiracion = minutos_expiracion
        self.rate_limiter = rate_limiter
        self.max_solicitudes_usuario = max_solicitudes_usuario
        self.max_solicitudes_ip = max_solicitudes_ip

    def ejecutar(
        self,
        dto: SolicitarRecuperacionDTO,
        clave_ip: str | None = None,
    ) -> Operacion2FAResponseDTO:
        usuario_str = NombreUsuario(dto.usuario).valor

        # Rate limiting anti-flooding por IP
        if clave_ip and self.rate_limiter is not None:
            k_ip = f"recup:ip:{clave_ip}"
            if not self.rate_limiter.permitir(k_ip, max_intentos=self.max_solicitudes_ip):
                raise DemasiadosIntentosError(
                    "Demasiadas solicitudes de recuperación desde esta dirección IP. Intente más tarde.",
                    usuario=usuario_str,
                    retry_after_seg=self.rate_limiter.segundos_restantes(k_ip, max_intentos=self.max_solicitudes_ip),
                )

        # Rate limiting anti-flooding por usuario
        if self.rate_limiter is not None:
            k_usr = f"recup:usr:{usuario_str}"
            if not self.rate_limiter.permitir(k_usr, max_intentos=self.max_solicitudes_usuario):
                raise DemasiadosIntentosError(
                    "Demasiadas solicitudes de recuperación para este usuario. Intente más tarde.",
                    usuario=usuario_str,
                    retry_after_seg=self.rate_limiter.segundos_restantes(
                        k_usr, max_intentos=self.max_solicitudes_usuario
                    ),
                )

        # Registrar intento en ambas dimensiones
        if self.rate_limiter is not None:
            self.rate_limiter.registrar_intento(f"recup:usr:{usuario_str}")
            if clave_ip:
                self.rate_limiter.registrar_intento(f"recup:ip:{clave_ip}")
        usuario = self.repositorio_usuarios.obtener_por_usuario(usuario_str)

        if usuario and usuario.esta_activo:
            ahora = datetime.now(timezone.utc)
            expira_en = ahora + timedelta(minutes=self.minutos_expiracion)
            token = self.generador_token.generar_recuperacion(
                usuario_id=usuario.id,
                usuario=usuario.usuario,
                expira_en=expira_en,
                hash_actual=usuario.hash_contrasena,
            )
            enlace = f"{self.frontend_url.rstrip('/')}/restablecer-contrasena?token={token}"
            self.servicio_email.enviar_email_recuperacion(usuario.usuario, enlace)

        # OWASP: Respuesta idéntica exista o no el usuario para mitigar enumeración
        return Operacion2FAResponseDTO(
            exito=True,
            mensaje="Si el usuario existe y está activo, se ha enviado un correo con instrucciones para restablecer la contraseña.",
        )


class RestablecerContrasenaUseCase:
    """Valida el token de recuperación y establece la nueva contraseña del usuario."""

    def __init__(
        self,
        repositorio_usuarios: RepositorioUsuariosPort,
        generador_token: GeneradorTokenPort,
        hash_service: HashContrasenaService,
        revocation_service: TokenRevocationService | None = None,
    ):
        self.repositorio_usuarios = repositorio_usuarios
        self.generador_token = generador_token
        self.hash_service = hash_service
        self.revocation_service = revocation_service

    def ejecutar(self, dto: RestablecerContrasenaDTO) -> Operacion2FAResponseDTO:
        payload = self.generador_token.verificar_recuperacion(dto.token)
        if payload is None:
            raise TokenRecuperacionInvalidoError("El token de restablecimiento es inválido o ha expirado.")

        usuario_id = payload.get("sub")
        if not usuario_id:
            raise TokenRecuperacionInvalidoError("Token de restablecimiento corrupto.")

        usuario = self.repositorio_usuarios.obtener_por_id(str(usuario_id))
        if not usuario or not usuario.esta_activo:
            raise TokenRecuperacionInvalidoError("El usuario ya no existe o está inactivo.")

        # Garantía de un solo uso mediante verificación de la huella de la clave actual
        pwh = hashlib.sha256(usuario.hash_contrasena.encode("utf-8")).hexdigest()[:16]
        if payload.get("pwh") != pwh:
            raise TokenRecuperacionInvalidoError("El token de restablecimiento ya ha sido utilizado.")

        if len(dto.nueva_contrasena) < 8:
            raise ContrasenaDebilError("La nueva contraseña debe tener al menos 8 caracteres.")

        usuario.hash_contrasena = self.hash_service.generar_hash(dto.nueva_contrasena)
        usuario.actualizado_en = datetime.now(timezone.utc)
        self.repositorio_usuarios.guardar(usuario)

        # Revocación inmediata de todas las sesiones activas previas
        if self.revocation_service is not None:
            self.revocation_service.revocar_usuario(usuario.id)

        return Operacion2FAResponseDTO(
            exito=True,
            mensaje="Contraseña actualizada exitosamente. Ya puedes iniciar sesión.",
        )

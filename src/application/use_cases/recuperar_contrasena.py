import hashlib
from datetime import datetime, timedelta, timezone

from src.application.dtos.auth_dto import (
    Operacion2FAResponseDTO,
    RestablecerContrasenaDTO,
    SolicitarRecuperacionDTO,
)
from src.domain.auth.exceptions import (
    ContrasenaDebilError,
    TokenRecuperacionInvalidoError,
)
from src.domain.auth.ports import (
    GeneradorTokenPort,
    RepositorioUsuariosPort,
    ServicioEmailPort,
)
from src.domain.auth.services import HashContrasenaService


class SolicitarRecuperacionContrasenaUseCase:
    """Inicia el flujo de recuperación de contraseña enviando un enlace por correo."""

    def __init__(
        self,
        repositorio_usuarios: RepositorioUsuariosPort,
        generador_token: GeneradorTokenPort,
        servicio_email: ServicioEmailPort,
        frontend_url: str = "https://www.datamaq.com.ar",
        minutos_expiracion: int = 15,
    ):
        self.repositorio_usuarios = repositorio_usuarios
        self.generador_token = generador_token
        self.servicio_email = servicio_email
        self.frontend_url = frontend_url
        self.minutos_expiracion = minutos_expiracion

    def ejecutar(self, dto: SolicitarRecuperacionDTO) -> Operacion2FAResponseDTO:
        usuario_str = dto.usuario.strip()
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
    ):
        self.repositorio_usuarios = repositorio_usuarios
        self.generador_token = generador_token
        self.hash_service = hash_service

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

        return Operacion2FAResponseDTO(
            exito=True,
            mensaje="Contraseña actualizada exitosamente. Ya puedes iniciar sesión.",
        )

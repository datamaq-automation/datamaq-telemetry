"""src/application/use_cases/gestionar_2fa.py."""

import uuid
from datetime import timedelta

from src.application.dtos.auth_dto import (
    Activar2FARequestDTO,
    Desactivar2FARequestDTO,
    LoginResponseDTO,
    Operacion2FAResponseDTO,
    Setup2FAResponseDTO,
    Verificar2FARequestDTO,
)
from src.domain.auth.entities import DispositivoConfiable, ahora_utc
from src.domain.auth.exceptions import (
    Codigo2FAInvalidoError,
    CredencialesInvalidasError,
    DemasiadosIntentosError,
    Operacion2FANoDisponibleParaInvitadoError,
    TokenMFAPendienteInvalidoError,
    UsuarioInactivoError,
)
from src.domain.auth.ports import (
    CifradorSecreto2FAPort,
    GeneradorTokenPort,
    RepositorioDispositivosConfiablesPort,
    RepositorioUsuariosPort,
    ServicioTOTPPort,
)
from src.domain.auth.services import (
    CodigosRespaldoService,
    HashContrasenaService,
    PoliticaExpiracionService,
    RateLimiterService,
    TokenDispositivoService,
)


class Verificar2FAUseCase:
    def __init__(
        self,
        repo_usuarios: RepositorioUsuariosPort,
        token_service: GeneradorTokenPort,
        totp_service: ServicioTOTPPort,
        cifrador_service: CifradorSecreto2FAPort,
        minutos_validez: int,
        rate_limiter: RateLimiterService | None = None,
        repo_dispositivos: RepositorioDispositivosConfiablesPort | None = None,
    ):
        self.repo_usuarios = repo_usuarios
        self.token_service = token_service
        self.totp_service = totp_service
        self.cifrador_service = cifrador_service
        self.minutos_validez = minutos_validez
        self.rate_limiter = rate_limiter
        self.repo_dispositivos = repo_dispositivos

    def _registrar_intento(self, clave: str) -> None:
        if self.rate_limiter is not None:
            self.rate_limiter.registrar_intento(clave)

    def verificar(
        self,
        dto: Verificar2FARequestDTO,
        clave_limite: str | None = None,
        ip_origen: str = "",
        user_agent: str = "",
        nombre_dispositivo: str | None = None,
    ) -> LoginResponseDTO:
        claims = self.token_service.verificar_mfa(dto.mfa_token)
        if not claims or not claims.get("usuario"):
            raise TokenMFAPendienteInvalidoError("Token MFA inválido o expirado.")

        usuario_nombre = str(claims["usuario"])
        clave = clave_limite if clave_limite is not None else f"2fa:{usuario_nombre}"

        if self.rate_limiter is not None and not self.rate_limiter.permitir(clave):
            raise DemasiadosIntentosError(
                "Demasiados intentos de verificación 2FA. Intente más tarde.",
                usuario=usuario_nombre,
                retry_after_seg=self.rate_limiter.segundos_restantes(clave),
            )

        usuario = self.repo_usuarios.obtener_por_usuario(usuario_nombre)
        if usuario is None or not usuario.esta_activo or not usuario.totp_enabled or not usuario.totp_secret:
            self._registrar_intento(clave)
            raise CredencialesInvalidasError("Credenciales o configuración 2FA inválida.", usuario=usuario_nombre)

        secreto_plano = self.cifrador_service.descifrar(usuario.totp_secret)
        codigo_valido = self.totp_service.verificar_codigo(secreto_plano, dto.codigo)

        if not codigo_valido and usuario.totp_backup_codes:
            codigo_valido, restantes = CodigosRespaldoService.verificar_y_consumir(
                dto.codigo, usuario.totp_backup_codes
            )
            if codigo_valido:
                usuario.totp_backup_codes = restantes
                self.repo_usuarios.guardar(usuario)

        if not codigo_valido:
            self._registrar_intento(clave)
            raise Codigo2FAInvalidoError("Código 2FA incorrecto.", usuario=usuario_nombre)

        if self.rate_limiter is not None:
            self.rate_limiter.resetear(clave)

        device_trust_token = None
        if dto.recordar_dispositivo and self.repo_dispositivos is not None:
            raw_secret = TokenDispositivoService.generar_secreto()
            token_hash = TokenDispositivoService.calcular_hash(raw_secret)
            ahora = ahora_utc()
            disp = DispositivoConfiable(
                id=str(uuid.uuid4()),
                usuario_id=usuario.id,
                token_hash=token_hash,
                nombre_dispositivo=nombre_dispositivo,
                user_agent=user_agent,
                ip_origen=ip_origen,
                creado_en=ahora,
                ultimo_acceso_en=ahora,
                expira_en=ahora + timedelta(days=30),
                revocado=False,
            )
            self.repo_dispositivos.guardar(disp)
            device_trust_token = raw_secret

        expira_en = PoliticaExpiracionService.calcular_expiracion(ahora_utc(), self.minutos_validez)
        token = self.token_service.generar(
            usuario.id, usuario.usuario, expira_en, rol=usuario.rol, organizacion_id=usuario.organizacion_id
        )
        return LoginResponseDTO(
            token=token,
            expira_en=expira_en,
            require_2fa=False,
            device_trust_token=device_trust_token,
        )


class Setup2FAUseCase:
    def __init__(
        self,
        repo_usuarios: RepositorioUsuariosPort,
        totp_service: ServicioTOTPPort,
    ):
        self.repo_usuarios = repo_usuarios
        self.totp_service = totp_service

    def ejecutar(self, usuario_nombre: str) -> Setup2FAResponseDTO:
        usuario = self.repo_usuarios.obtener_por_usuario(usuario_nombre)
        if usuario is None or not usuario.esta_activo:
            raise UsuarioInactivoError("Usuario inexistente o inactivo.", usuario=usuario_nombre)
        # TODO(#65): quitar cuando el frontend de main de app-datamaq deje de llamar a estos roles.
        if usuario.rol in ("invitado", "invitado_global"):
            raise Operacion2FANoDisponibleParaInvitadoError("2fa_no_disponible_para_invitado", usuario=usuario_nombre)

        secret = self.totp_service.generar_secreto()
        backup_codes = CodigosRespaldoService.generar_codigos(8)
        uri = self.totp_service.generar_uri(usuario.usuario, secret, emisor="DataMaq")
        qr_svg = self.totp_service.generar_qr_svg(uri)

        return Setup2FAResponseDTO(
            secret=secret,
            uri=uri,
            qr_svg=qr_svg,
            backup_codes=backup_codes,
        )


class Activar2FAUseCase:
    def __init__(
        self,
        repo_usuarios: RepositorioUsuariosPort,
        totp_service: ServicioTOTPPort,
        cifrador_service: CifradorSecreto2FAPort,
    ):
        self.repo_usuarios = repo_usuarios
        self.totp_service = totp_service
        self.cifrador_service = cifrador_service

    def ejecutar(self, usuario_nombre: str, dto: Activar2FARequestDTO) -> Operacion2FAResponseDTO:
        usuario = self.repo_usuarios.obtener_por_usuario(usuario_nombre)
        if usuario is None or not usuario.esta_activo:
            raise UsuarioInactivoError("Usuario inexistente o inactivo.", usuario=usuario_nombre)
        # TODO(#65): quitar cuando el frontend de main de app-datamaq deje de llamar a estos roles.
        if usuario.rol in ("invitado", "invitado_global"):
            raise Operacion2FANoDisponibleParaInvitadoError("2fa_no_disponible_para_invitado", usuario=usuario_nombre)

        if not self.totp_service.verificar_codigo(dto.secret, dto.codigo):
            raise Codigo2FAInvalidoError("Código TOTP inválido para activación.", usuario=usuario_nombre)

        hashes_backup = [CodigosRespaldoService.hashear(c) for c in dto.backup_codes]
        secreto_cifrado = self.cifrador_service.cifrar(dto.secret)

        usuario.totp_secret = secreto_cifrado
        usuario.totp_enabled = True
        usuario.totp_backup_codes = hashes_backup
        self.repo_usuarios.guardar(usuario)

        return Operacion2FAResponseDTO(exito=True, mensaje="2FA activado correctamente.")


class Desactivar2FAUseCase:
    def __init__(
        self,
        repo_usuarios: RepositorioUsuariosPort,
        hash_service: HashContrasenaService,
        totp_service: ServicioTOTPPort,
        cifrador_service: CifradorSecreto2FAPort,
    ):
        self.repo_usuarios = repo_usuarios
        self.hash_service = hash_service
        self.totp_service = totp_service
        self.cifrador_service = cifrador_service

    def ejecutar(self, usuario_nombre: str, dto: Desactivar2FARequestDTO) -> Operacion2FAResponseDTO:
        usuario = self.repo_usuarios.obtener_por_usuario(usuario_nombre)
        if usuario is None or not usuario.esta_activo:
            raise UsuarioInactivoError("Usuario inexistente o inactivo.", usuario=usuario_nombre)
        # TODO(#65): quitar cuando el frontend de main de app-datamaq deje de llamar a estos roles.
        if usuario.rol in ("invitado", "invitado_global"):
            raise Operacion2FANoDisponibleParaInvitadoError("2fa_no_disponible_para_invitado", usuario=usuario_nombre)

        if not self.hash_service.verificar(dto.contrasena, usuario.hash_contrasena):
            raise CredencialesInvalidasError("Contraseña incorrecta.", usuario=usuario_nombre)

        if not usuario.totp_enabled or not usuario.totp_secret:
            return Operacion2FAResponseDTO(exito=True, mensaje="2FA ya se encontraba desactivado.")

        secreto_plano = self.cifrador_service.descifrar(usuario.totp_secret)
        codigo_valido = self.totp_service.verificar_codigo(secreto_plano, dto.codigo)

        if not codigo_valido and usuario.totp_backup_codes:
            codigo_valido, _ = CodigosRespaldoService.verificar_y_consumir(dto.codigo, usuario.totp_backup_codes)

        if not codigo_valido:
            raise Codigo2FAInvalidoError("Código 2FA incorrecto para desactivación.", usuario=usuario_nombre)

        usuario.totp_secret = None
        usuario.totp_enabled = False
        usuario.totp_backup_codes = None
        self.repo_usuarios.guardar(usuario)

        return Operacion2FAResponseDTO(exito=True, mensaje="2FA desactivado correctamente.")

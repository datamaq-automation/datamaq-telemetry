"""src/application/use_cases/cambio_contrasena.py.

Casos de uso del cambio de contraseña autenticado con código OTP por email."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.exceptions import (
    CodigoCambioInvalidoError,
    ContrasenaDebilError,
    CredencialesInvalidasError,
    DemasiadosIntentosError,
    NoSePudoEnviarCodigoError,
)
from src.domain.auth.ports import RepositorioCambioContrasenaPort, RepositorioUsuariosPort, ServicioEmailPort
from src.domain.auth.services import HashContrasenaService
from src.domain.usuarios.servicios_contrasena import GeneradorCodigoOTP, ServicioTTLValidacion, ValidadorContraseña


@dataclass(frozen=True)
class SolicitudCambioCodigoResultado:
    email_destino: str


def _ofuscar_email(email: str) -> str:
    local, _, dominio = email.partition("@")
    return f"{local[:3]}...@{dominio}"


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class SolicitarCambioContrasenaUseCase:
    """Valida la contraseña actual, aplica el límite de solicitudes y envía el código por email."""

    def __init__(
        self,
        repo: RepositorioCambioContrasenaPort,
        usuarios: RepositorioUsuariosPort,
        hash_service: type[HashContrasenaService],
        email: ServicioEmailPort,
        clave_otp: str,
        codigo_service: type[GeneradorCodigoOTP] = GeneradorCodigoOTP,
        ahora: Callable[[], datetime] = _ahora_utc,
    ):
        self.repo = repo
        self.usuarios = usuarios
        self.hash_service = hash_service
        self.email = email
        self.clave_otp = clave_otp
        self.codigo_service = codigo_service
        self.ahora = ahora

    def ejecutar(
        self,
        usuario_id: str,
        password_actual: str,
        ip: str | None,
        user_agent: str | None,
    ) -> SolicitudCambioCodigoResultado:
        ahora = self.ahora()
        usuario = self.usuarios.obtener_por_id(usuario_id)
        if usuario is None or not usuario.esta_activo:
            raise CredencialesInvalidasError("Usuario no válido")

        # El límite va ANTES de verificar la contraseña: si no, cada intento erróneo seguiría sin costo.
        desde = ServicioTTLValidacion.inicio_ventana_solicitudes(ahora)
        consumidas = self.repo.contar_solicitudes_desde(usuario_id, desde) + self.repo.contar_auditoria_desde(
            usuario_id, "intento_fallido", desde
        )
        if consumidas >= ServicioTTLValidacion.MAX_SOLICITUDES:
            raise DemasiadosIntentosError(
                "Demasiadas solicitudes de código. Espere 10 minutos.",
                usuario=usuario.usuario,
                retry_after_seg=ServicioTTLValidacion.VENTANA_SOLICITUDES_MINUTOS * 60,
            )

        if not self.hash_service.verificar(password_actual, usuario.hash_contrasena):
            self.repo.registrar_auditoria(usuario_id, "intento_fallido", ip, user_agent, ahora)
            raise CredencialesInvalidasError("Contraseña actual incorrecta")

        # Solo vale el último código: cada solicitud invalida las anteriores.
        self.repo.invalidar_vigentes(usuario_id, ahora)
        codigo = self.codigo_service.generar()
        self.repo.crear_validacion(
            usuario_id,
            self.codigo_service.calcular_hmac(codigo, self.clave_otp),
            ahora + timedelta(minutes=ServicioTTLValidacion.TTL_MINUTOS),
            ahora,
        )

        if not self.email.enviar_codigo_cambio_contrasena(usuario.usuario, codigo):
            raise NoSePudoEnviarCodigoError("No se pudo enviar el código. Intente nuevamente.")

        self.repo.registrar_auditoria(usuario_id, "codigo_solicitado", ip, user_agent, ahora)
        return SolicitudCambioCodigoResultado(email_destino=_ofuscar_email(usuario.usuario))


class ConfirmarCambioContrasenaUseCase:
    """Valida el código (con límite de intentos), la política de contraseña y aplica el cambio."""

    def __init__(
        self,
        repo: RepositorioCambioContrasenaPort,
        usuarios: RepositorioUsuariosPort,
        hash_service: type[HashContrasenaService],
        email: ServicioEmailPort,
        clave_otp: str,
        codigo_service: type[GeneradorCodigoOTP] = GeneradorCodigoOTP,
        ahora: Callable[[], datetime] = _ahora_utc,
    ):
        self.repo = repo
        self.usuarios = usuarios
        self.hash_service = hash_service
        self.email = email
        self.clave_otp = clave_otp
        self.codigo_service = codigo_service
        self.ahora = ahora

    def ejecutar(
        self,
        usuario_id: str,
        codigo: str,
        password_nueva: str,
        ip: str | None,
        user_agent: str | None,
    ) -> None:
        ahora = self.ahora()
        usuario = self.usuarios.obtener_por_id(usuario_id)
        if usuario is None or not usuario.esta_activo:
            raise CredencialesInvalidasError("Usuario no válido")

        validacion = self.repo.obtener_vigente(usuario_id, ahora)
        if validacion is None:
            raise CodigoCambioInvalidoError("Código inválido o expirado")

        if not self.codigo_service.verificar(codigo, validacion.codigo_hash, self.clave_otp):
            intentos = self.repo.registrar_intento_fallido(validacion.id)
            self.repo.registrar_auditoria(usuario_id, "intento_fallido", ip, user_agent, ahora)
            if intentos >= ServicioTTLValidacion.MAX_INTENTOS_CODIGO:
                self.repo.consumir(validacion.id, ahora)
                self.repo.registrar_auditoria(usuario_id, "bloqueo_por_intentos", ip, user_agent, ahora)
            raise CodigoCambioInvalidoError("Código inválido o expirado")

        self._validar_contrasena_nueva(usuario, password_nueva)

        self.repo.registrar_auditoria(usuario_id, "codigo_validado", ip, user_agent, ahora)
        self.repo.consumir(validacion.id, ahora)
        usuario.hash_contrasena = self.hash_service.generar_hash(password_nueva)
        usuario.sesiones_revocadas_antes_de = ahora
        usuario.actualizado_en = ahora
        self.usuarios.guardar(usuario)
        self.repo.registrar_auditoria(usuario_id, "cambio_exitoso", ip, user_agent, ahora)

        # El cambio ya ocurrió: un fallo al notificar no lo revierte.
        self.email.notificar_cambio_contrasena(usuario.usuario, ahora, ip)

    def _validar_contrasena_nueva(self, usuario: UsuarioAuth, password_nueva: str) -> None:
        es_valida, errores = ValidadorContraseña.validar(password_nueva)
        if not es_valida:
            raise ContrasenaDebilError("La nueva contraseña no cumple: " + ", ".join(errores))
        if self.hash_service.verificar(password_nueva, usuario.hash_contrasena):
            raise ContrasenaDebilError("La nueva contraseña no puede ser igual a la actual.")

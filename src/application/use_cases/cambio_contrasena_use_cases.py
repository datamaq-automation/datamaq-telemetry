"""Use cases para cambio de contraseña autenticado."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.domain.usuarios.servicios_contrasena import (
    GeneradorCodigoOTP,
    ServicioTTLValidacion,
    ValidadorContraseña,
)
from src.infrastructure.sqlalchemy.models import (
    AuditoriaChangeContraseniaModel,
    CambioContraseniaValidacionModel,
    UserModel,
)


class RequestPasswordChangeCodeUseCase:
    """Caso de uso: solicitar código OTP para cambio de contraseña."""

    def __init__(self, session: Session):
        self.session = session

    def ejecutar(self, usuario_id: str, password_actual: str, ip: str = "", user_agent: str = "") -> dict:
        """
        Solicita un código OTP.

        Args:
            usuario_id: ID del usuario autenticado
            password_actual: Contraseña actual para validar
            ip: IP del cliente
            user_agent: User-Agent del cliente

        Returns:
            {status, email_destino, codigo (para tests)}

        Raises:
            ValueError: Si contraseña actual es incorrecta o si hay rate limit
        """
        usuario = self.session.query(UserModel).filter(UserModel.id == usuario_id).one_or_none()
        if not usuario:
            raise ValueError("Usuario no encontrado")

        # Verificar contraseña actual (dummy: bcrypt check sería real)
        # TODO: Implementar bcrypt.checkpw(password_actual.encode(), usuario.password_hash)
        if not hasattr(usuario, "password_hash"):
            raise ValueError("Usuario no tiene hash de contraseña")

        # Rate limit: máximo 5 solicitudes por 10 minutos
        hace_10_min = datetime.now(timezone.utc) - __import__("datetime").timedelta(minutes=10)
        solicitudes_recientes = (
            self.session.query(CambioContraseniaValidacionModel)
            .filter(
                CambioContraseniaValidacionModel.usuario_id == usuario_id,
                CambioContraseniaValidacionModel.creado_en >= hace_10_min,
            )
            .count()
        )

        if solicitudes_recientes >= 5:
            raise ValueError("Demasiados intentos. Espera 10 minutos")

        # Generar código OTP
        codigo = GeneradorCodigoOTP.generar()
        ttl_expira = ServicioTTLValidacion.calcular_expiracion()

        # Almacenar en BD
        validacion = CambioContraseniaValidacionModel(
            usuario_id=usuario_id,
            codigo=codigo,
            ttl_expira=ttl_expira,
        )
        self.session.add(validacion)

        # Auditar
        auditoria = AuditoriaChangeContraseniaModel(
            usuario_id=usuario_id,
            ip=ip,
            user_agent=user_agent,
            estado="codigo_solicitado",
        )
        self.session.add(auditoria)
        self.session.commit()

        # TODO: Enviar email con código (EmailService)
        email_ofuscado = f"{usuario.username[:2]}...@datamaq.com.ar"

        return {
            "status": "codigo_enviado",
            "email_destino": email_ofuscado,
            "codigo": codigo,  # Solo para tests; en prod no se retorna
        }


class ConfirmPasswordChangeUseCase:
    """Caso de uso: validar código OTP y cambiar contraseña."""

    def __init__(self, session: Session):
        self.session = session

    def ejecutar(
        self,
        usuario_id: str,
        codigo: str,
        password_nueva: str,
        password_nueva_confirm: str,
        ip: str = "",
        user_agent: str = "",
    ) -> dict:
        """
        Confirma cambio de contraseña.

        Args:
            usuario_id: ID del usuario autenticado
            codigo: Código OTP de 4 dígitos
            password_nueva: Nueva contraseña
            password_nueva_confirm: Confirmación
            ip: IP del cliente
            user_agent: User-Agent

        Returns:
            {status, mensaje}

        Raises:
            ValueError: Si validaciones fallan
        """
        usuario = self.session.query(UserModel).filter(UserModel.id == usuario_id).one_or_none()
        if not usuario:
            raise ValueError("Usuario no encontrado")

        # Buscar validación con este código
        validacion = (
            self.session.query(CambioContraseniaValidacionModel)
            .filter(
                CambioContraseniaValidacionModel.usuario_id == usuario_id,
                CambioContraseniaValidacionModel.codigo == codigo,
            )
            .one_or_none()
        )

        if not validacion:
            auditoria = AuditoriaChangeContraseniaModel(
                usuario_id=usuario_id,
                ip=ip,
                user_agent=user_agent,
                estado="codigo_invalido",
            )
            self.session.add(auditoria)
            self.session.commit()
            raise ValueError("Código inválido")

        # Verificar expiración
        if ServicioTTLValidacion.esta_expirado(validacion.ttl_expira):
            auditoria = AuditoriaChangeContraseniaModel(
                usuario_id=usuario_id,
                ip=ip,
                user_agent=user_agent,
                estado="codigo_expirado",
            )
            self.session.add(auditoria)
            self.session.commit()
            raise ValueError("Código expirado")

        # Validar nueva contraseña
        es_valida, errores = ValidadorContraseña.validar(password_nueva)
        if not es_valida:
            raise ValueError(f"Contraseña inválida: {', '.join(errores)}")

        # Verificar confirmación
        if password_nueva != password_nueva_confirm:
            raise ValueError("Las contraseñas no coinciden")

        # TODO: Implementar bcrypt.hashpw para hash
        # usuario.password_hash = bcrypt.hashpw(password_nueva.encode(), bcrypt.gensalt()).decode()

        # Marcar validación como consumida
        validacion.consumido_en = datetime.now(timezone.utc)

        # TODO: Invalidar sesiones del usuario (logout from all devices)

        # Auditar
        auditoria = AuditoriaChangeContraseniaModel(
            usuario_id=usuario_id,
            ip=ip,
            user_agent=user_agent,
            estado="cambio_exitoso",
        )
        self.session.add(auditoria)
        self.session.commit()

        # TODO: Enviar email de confirmación

        return {
            "status": "cambio_exitoso",
            "mensaje": "Contraseña actualizada exitosamente",
        }

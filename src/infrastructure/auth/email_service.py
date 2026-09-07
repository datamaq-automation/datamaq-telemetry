import smtplib
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

import structlog

from src.domain.auth.ports import ServicioEmailPort

logger = structlog.get_logger("email_service")


class SmtpEmailService(ServicioEmailPort):
    """Servicio de envío de correos vía SMTP utilizando la biblioteca estándar de Python."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 25,
        user: str = "",
        password: str = "",
        use_tls: bool = False,
        from_email: str = "no-reply@datamaq.com.ar",
        app_env: str = "production",
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_tls = use_tls
        self.from_email = from_email
        self.app_env = app_env

    def enviar_email_recuperacion(self, destinatario: str, enlace_restablecimiento: str) -> bool:
        if self.app_env == "test":
            logger.info(
                "email_simulado_test",
                destinatario=destinatario,
                enlace=enlace_restablecimiento,
            )
            return True

        msg = EmailMessage()
        msg["Subject"] = "Recuperación de contraseña - Datamaq Telemetry"
        msg["From"] = formataddr(("Datamaq Telemetry", self.from_email))
        msg["To"] = formataddr(("", destinatario))
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="datamaq.com.ar")

        texto_plano = (
            f"Hola,\n\n"
            f"Has solicitado restablecer tu contraseña en Datamaq Telemetry.\n"
            f"Para definir una nueva contraseña, haz clic en el siguiente enlace o cópialo en tu navegador:\n\n"
            f"{enlace_restablecimiento}\n\n"
            f"Este enlace tiene una validez de 15 minutos y es de un solo uso.\n"
            f"Si no has solicitado este restablecimiento, puedes ignorar este correo de forma segura.\n\n"
            f"Atentamente,\n"
            f"El equipo de Datamaq"
        )
        msg.set_content(texto_plano)

        html_content = (
            f"<!DOCTYPE html>\n"
            f"<html lang='es'>\n"
            f"<head><meta charset='utf-8'></head>\n"
            f"<body style='font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; padding: 20px;'>\n"
            f"  <div style='max-width: 540px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; padding: 32px;'>\n"
            f"    <div style='font-size: 20px; font-weight: bold; color: #0284c7; margin-bottom: 24px;'>⚡ Datamaq Telemetry</div>\n"
            f"    <h2 style='font-size: 18px; margin-bottom: 16px;'>Restablecimiento de Contraseña</h2>\n"
            f"    <p>Hola,</p>\n"
            f"    <p>Hemos recibido una solicitud para restablecer la contraseña de tu cuenta.</p>\n"
            f"    <div style='text-align: center; margin: 28px 0;'>\n"
            f"      <a href='{enlace_restablecimiento}' style='display: inline-block; background-color: #0284c7; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600;' target='_blank'>Restablecer mi Contraseña</a>\n"
            f"    </div>\n"
            f"    <p style='font-size: 13px; color: #64748b;'>O copia y pega el siguiente enlace en tu navegador:<br><a href='{enlace_restablecimiento}' style='color: #0284c7; word-break: break-all;'>{enlace_restablecimiento}</a></p>\n"
            f"    <hr style='border: none; border-top: 1px solid #e2e8f0; margin-top: 32px;'>\n"
            f"    <p style='font-size: 12px; color: #64748b;'>Este enlace tiene una validez de <strong>15 minutos</strong> y puede usarse una única vez.<br>Si no has solicitado este cambio, puedes ignorar este correo de forma segura.</p>\n"
            f"  </div>\n"
            f"</body>\n"
            f"</html>"
        )
        msg.add_alternative(html_content, subtype="html")

        try:
            with smtplib.SMTP(self.host, self.port, local_hostname="datamaq.com.ar", timeout=10) as server:
                if self.use_tls:
                    server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.send_message(msg)
            logger.info("email_recuperacion_enviado", destinatario=destinatario)
            return True
        except Exception as exc:
            logger.error("email_recuperacion_fallido", error=str(exc), destinatario=destinatario)
            return False

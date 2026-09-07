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
        msg["To"] = destinatario
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="datamaq.com.ar")
        msg["X-Mailer"] = "Datamaq Telemetry Mailer 1.0"

        texto_plano = (
            f"Estimado usuario,\n\n"
            f"Hemos recibido una solicitud para restablecer la contraseña asociada a su cuenta "
            f"en la plataforma Datamaq Telemetry.\n\n"
            f"Para definir una nueva contraseña de acceso segura, ingrese al siguiente enlace:\n"
            f"{enlace_restablecimiento}\n\n"
            f"Información de seguridad importante:\n"
            f"- Este enlace es de un solo uso y caduca automáticamente a los 15 minutos de su emisión.\n"
            f"- Si usted no realizó esta solicitud, puede desestimar este mensaje de forma segura. "
            f"Su contraseña actual no ha sido modificada y su cuenta permanece protegida.\n"
            f"- Ante cualquier duda o inconveniente técnico, comuníquese con el administrador del sistema.\n\n"
            f"Atentamente,\n"
            f"El equipo de Soporte y Seguridad de Datamaq Telemetry"
        )
        msg.set_content(texto_plano)

        html_content = (
            f"<!DOCTYPE html>\n"
            f"<html lang='es'>\n"
            f"<head><meta charset='utf-8'></head>\n"
            f"<body style='font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; padding: 24px;'>\n"
            f"  <div style='max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; padding: 32px;'>\n"
            f"    <div style='font-size: 22px; font-weight: bold; color: #0284c7; margin-bottom: 20px;'>⚡ Datamaq Telemetry</div>\n"
            f"    <h2 style='font-size: 18px; margin-bottom: 16px; color: #0f172a;'>Solicitud de Restablecimiento de Contraseña</h2>\n"
            f"    <p>Estimado usuario,</p>\n"
            f"    <p>Hemos recibido una solicitud para restablecer la contraseña asociada a su cuenta en la plataforma de telemetría y gestión energética Datamaq.</p>\n"
            f"    <p>Para definir una nueva contraseña de acceso segura, haga clic en el botón a continuación:</p>\n"
            f"    <div style='text-align: center; margin: 28px 0;'>\n"
            f"      <a href='{enlace_restablecimiento}' style='display: inline-block; background-color: #0284c7; color: #ffffff; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-weight: 600;' target='_blank'>Restablecer Contraseña</a>\n"
            f"    </div>\n"
            f"    <p style='font-size: 13px; color: #64748b;'>Si el botón no funciona, copie y pegue la siguiente dirección en la barra de su navegador:<br><span style='word-break: break-all; color: #0284c7;'>{enlace_restablecimiento}</span></p>\n"
            f"    <hr style='border: none; border-top: 1px solid #e2e8f0; margin: 28px 0;'>\n"
            f"    <p style='font-size: 12px; color: #64748b; line-height: 1.5;'>\n"
            f"      <strong>Aviso de seguridad:</strong> Este enlace tiene una vigencia de <strong>15 minutos</strong> y quedará invalidado automáticamente tras su primer uso.<br>\n"
            f"      Si usted no solicitó este cambio, ignore este correo. Su contraseña actual no ha sido modificada y su cuenta permanece protegida con todas sus medidas de seguridad habituales.\n"
            f"    </p>\n"
            f"  </div>\n"
            f"</body>\n"
            f"</html>"
        )
        msg.add_alternative(html_content, subtype="html")

        try:
            with smtplib.SMTP(self.host, self.port, local_hostname="datamaq.com.ar", timeout=10) as server:
                server.ehlo("datamaq.com.ar")
                if self.use_tls:
                    server.starttls()
                    server.ehlo("datamaq.com.ar")
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.send_message(msg)
            logger.info("email_recuperacion_enviado", destinatario=destinatario)
            return True
        except Exception as exc:
            logger.error("email_recuperacion_fallido", error=str(exc), destinatario=destinatario)
            return False

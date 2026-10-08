"""src/infrastructure/auth/email_service.py."""

import smtplib
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

import structlog

from src.domain.auth.ports import ServicioEmailPort
from src.domain.telemetria.entities import AlertaDispositivo, Dispositivo
from src.domain.telemetria.ports import NotificadorAlertasPort

logger = structlog.get_logger("email_service")


class SmtpEmailService(ServicioEmailPort, NotificadorAlertasPort):
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
        return self._enviar_smtp(msg, "email_recuperacion", destinatario)

    def enviar_codigo_cambio_contrasena(self, destinatario: str, codigo: str) -> bool:
        if self.app_env == "test":
            # Sin el código: los logs no deben contenerlo (ni siquiera en modo simulado).
            logger.info("email_simulado_test", destinatario=destinatario, asunto="cambio_contrasena_codigo")
            return True
        msg = EmailMessage()
        msg["Subject"] = "Confirmación: Cambiar Contraseña en DataMaq"
        msg["From"] = formataddr(("Datamaq Telemetry", self.from_email))
        msg["To"] = destinatario
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="datamaq.com.ar")
        msg["X-Mailer"] = "Datamaq Telemetry Mailer 1.0"
        msg.set_content(
            "Estimado usuario,\n\n"
            "Recibimos una solicitud para cambiar la contraseña de su cuenta en Datamaq Telemetry.\n\n"
            f"Su código de validación es: {codigo}\n\n"
            "El código vence en 10 minutos y sólo puede usarse una vez.\n"
            "Si usted no realizó esta solicitud, ignore este mensaje: su contraseña no fue modificada.\n\n"
            "Atentamente,\nEl equipo de Soporte y Seguridad de Datamaq Telemetry"
        )
        return self._enviar_smtp(msg, "email_cambio_contrasena_codigo", destinatario)

    def notificar_cambio_contrasena(self, destinatario: str, momento: datetime, ip: str | None) -> bool:
        if self.app_env == "test":
            logger.info("email_simulado_test", destinatario=destinatario, asunto="cambio_contrasena_confirmado")
            return True
        msg = EmailMessage()
        msg["Subject"] = "Contraseña cambiada - Datamaq Telemetry"
        msg["From"] = formataddr(("Datamaq Telemetry", self.from_email))
        msg["To"] = destinatario
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="datamaq.com.ar")
        msg["X-Mailer"] = "Datamaq Telemetry Mailer 1.0"
        msg.set_content(
            "Estimado usuario,\n\n"
            f"Su contraseña de Datamaq Telemetry fue cambiada el {momento.isoformat()} "
            f"desde la IP {ip or 'desconocida'}.\n"
            "Todas sus sesiones activas fueron cerradas: deberá volver a iniciar sesión.\n\n"
            "Si no fue usted, comuníquese de inmediato con el administrador del sistema.\n\n"
            "Atentamente,\nEl equipo de Soporte y Seguridad de Datamaq Telemetry"
        )
        return self._enviar_smtp(msg, "email_cambio_contrasena_confirmado", destinatario)

    def _enviar_smtp(self, msg: EmailMessage, log_event: str, destinatario: str) -> bool:
        try:
            with smtplib.SMTP(self.host, self.port, local_hostname="datamaq.com.ar", timeout=10) as server:
                server.ehlo("datamaq.com.ar")
                if self.use_tls:
                    server.starttls()
                    server.ehlo("datamaq.com.ar")
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.send_message(msg)
            logger.info(f"{log_event}_enviado", destinatario=destinatario)
            return True
        except Exception as exc:
            logger.error(f"{log_event}_fallido", error=str(exc), destinatario=destinatario)
            return False

    def notificar_alerta_critica(
        self,
        alerta: AlertaDispositivo,
        dispositivo: Dispositivo,
        destinatarios: list[str],
    ) -> bool:
        if not destinatarios:
            return False
        if self.app_env == "test":
            logger.info(
                "email_alerta_simulado_test",
                dispositivo=dispositivo.id,
                tipo_alerta=alerta.tipo_alerta,
                destinatarios=destinatarios,
            )
            return True

        msg = _construir_mensaje_alerta_critica(alerta, dispositivo, destinatarios, self.from_email)
        return self._enviar_smtp(msg, "email_alerta_critica", ", ".join(destinatarios))


def _construir_mensaje_alerta_critica(
    alerta: AlertaDispositivo,
    dispositivo: Dispositivo,
    destinatarios: list[str],
    from_email: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = f"🚨 [CRÍTICA] Alerta Eléctrica en {dispositivo.nombre} — {alerta.tipo_alerta}"
    msg["From"] = formataddr(("Datamaq Telemetry Alerting", from_email))
    msg["To"] = ", ".join(destinatarios)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="datamaq.com.ar")
    msg["X-Mailer"] = "Datamaq Telemetry Alerting 1.0"
    msg["Auto-Submitted"] = "auto-generated"
    msg["X-Auto-Response-Suppress"] = "All"
    msg["Precedence"] = "bulk"

    fecha_utc = alerta.disparada_en.strftime("%Y-%m-%d %H:%M:%S UTC")
    medido = f"{alerta.valor_medido} {alerta.unidad or ''}".strip() if alerta.valor_medido is not None else "N/A"
    umbral = f"{alerta.valor_umbral} {alerta.unidad or ''}".strip() if alerta.valor_umbral is not None else "N/A"
    fase = alerta.fase or "Trifásica / Red"

    texto_plano = (
        f"ALERTA CRÍTICA DE CALIDAD DE ENERGÍA - DATAMAQ TELEMETRY\n"
        f"----------------------------------------------------------\n"
        f"Dispositivo: {dispositivo.nombre} ({dispositivo.device_uid.valor})\n"
        f"Tipo de Alerta: {alerta.tipo_alerta}\n"
        f"Severidad: CRÍTICA\n"
        f"Fase Afectada: {fase}\n"
        f"Valor Medido: {medido}\n"
        f"Valor Umbral: {umbral}\n"
        f"Fecha y Hora: {fecha_utc}\n"
        f"Detalle: {alerta.mensaje}\n\n"
        f"Acción recomendada: Ingrese a https://www.datamaq.com.ar para inspeccionar el estado del tablero.\n"
    )
    msg.set_content(texto_plano)

    html_content = (
        f"<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'></head>"
        f"<body style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;background-color:#f8fafc;color:#1e293b;padding:20px;'>"
        f"<div style='max-width:580px;margin:0 auto;background:#fff;border-radius:8px;border:1px solid #e2e8f0;padding:28px;'>"
        f"<div style='font-size:20px;font-weight:bold;color:#0284c7;margin-bottom:16px;'>⚡ Datamaq Telemetry</div>"
        f"<div style='background-color:#fee2e2;border-left:4px solid #ef4444;padding:12px 16px;border-radius:4px;margin-bottom:20px;'>"
        f"<strong style='color:#b91c1c;font-size:15px;'>🚨 Alerta Eléctrica Crítica</strong>"
        f"<div style='color:#7f1d1d;font-size:13px;margin-top:4px;'>{alerta.mensaje}</div></div>"
        f"<table style='width:100%;border-collapse:collapse;margin-bottom:20px;font-size:14px;'>"
        f"<tr><td style='padding:6px 0;color:#64748b;width:35%;'>Dispositivo:</td><td style='font-weight:600;'>{dispositivo.nombre} ({dispositivo.device_uid.valor})</td></tr>"
        f"<tr><td style='padding:6px 0;color:#64748b;'>Tipo de anomalía:</td><td style='font-weight:600;color:#ef4444;'>{alerta.tipo_alerta}</td></tr>"
        f"<tr><td style='padding:6px 0;color:#64748b;'>Fase afectada:</td><td>{fase}</td></tr>"
        f"<tr><td style='padding:6px 0;color:#64748b;'>Valor registrado:</td><td><strong>{medido}</strong> (Umbral: {umbral})</td></tr>"
        f"<tr><td style='padding:6px 0;color:#64748b;'>Fecha y Hora:</td><td>{fecha_utc}</td></tr></table>"
        f"<hr style='border:none;border-top:1px solid #e2e8f0;margin:20px 0;'>"
        f"<p style='font-size:12px;color:#64748b;'>Aviso automático generado por el motor de telemetría de Datamaq. No responda a este correo.</p>"
        f"</div></body></html>"
    )
    msg.add_alternative(html_content, subtype="html")
    return msg

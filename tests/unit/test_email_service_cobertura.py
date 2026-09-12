"""tests/unit/test_email_service_cobertura.py — Suite de pruebas unitarias para SmtpEmailService."""

import smtplib
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.domain.telemetria.entities import AlertaDispositivo, Dispositivo
from src.domain.telemetria.value_objects import MacAddress, SeveridadAlerta
from src.infrastructure.auth.email_service import (
    SmtpEmailService,
    _construir_mensaje_alerta_critica,
)
from src.infrastructure.fastapi.dependencies import (
    get_email_service,
    get_email_service_singleton,
)
from src.infrastructure.settings.config import Settings

# ---------------------------------------------------------------------------
# Fixtures y Helpers
# ---------------------------------------------------------------------------


def _crear_dispositivo(
    nombre: str = "Compresor Principal",
    mac: str = "AA:BB:CC:11:22:33",
) -> Dispositivo:
    return Dispositivo(
        id="dev-test-100",
        device_uid=MacAddress(mac),
        nombre=nombre,
    )


def _crear_alerta(
    tipo_alerta: str = "SOBRETENSION",
    fase: str | None = "Fase R",
    valor_medido: float | None = 255.0,
    valor_umbral: float | None = 240.0,
    unidad: str | None = "V",
    mensaje: str = "Tensión anormal detectada en fase principal",
    disparada_en: datetime | None = None,
) -> AlertaDispositivo:
    return AlertaDispositivo(
        id=42,
        dispositivo_id="dev-test-100",
        tipo_alerta=tipo_alerta,
        severidad=SeveridadAlerta.CRITICAL,
        mensaje=mensaje,
        disparada_en=disparada_en or datetime(2026, 9, 12, 10, 30, 0, tzinfo=timezone.utc),
        fase=fase,
        valor_medido=valor_medido,
        valor_umbral=valor_umbral,
        unidad=unidad,
    )


@pytest.fixture
def mock_smtp():
    """Mock context manager de smtplib.SMTP."""
    with patch("smtplib.SMTP") as mock_cls:
        mock_server = MagicMock()
        mock_cls.return_value.__enter__.return_value = mock_server
        mock_cls.return_value.__exit__.return_value = False
        yield mock_cls, mock_server


# ---------------------------------------------------------------------------
# 1. Inicialización y Valores por Defecto
# ---------------------------------------------------------------------------


class TestSmtpEmailServiceInicializacion:
    def test_init_valores_por_defecto(self):
        service = SmtpEmailService()
        assert service.host == "127.0.0.1"
        assert service.port == 25
        assert service.user == ""
        assert service.password == ""
        assert service.use_tls is False
        assert service.from_email == "no-reply@datamaq.com.ar"
        assert service.app_env == "production"

    def test_init_valores_personalizados(self):
        service = SmtpEmailService(
            host="smtp.corp.local",
            port=587,
            user="notificador",
            password="PasswordSegura2026!",
            use_tls=True,
            from_email="alertas@corp.local",
            app_env="staging",
        )
        assert service.host == "smtp.corp.local"
        assert service.port == 587
        assert service.user == "notificador"
        assert service.password == "PasswordSegura2026!"
        assert service.use_tls is True
        assert service.from_email == "alertas@corp.local"
        assert service.app_env == "staging"


# ---------------------------------------------------------------------------
# 2. Modo Simulado en Entorno de Test (app_env == "test")
# ---------------------------------------------------------------------------


class TestModoTestSimulado:
    def test_recuperacion_modo_test_no_conecta_smtp(self, mock_smtp):
        mock_cls, _ = mock_smtp
        service = SmtpEmailService(app_env="test")

        resultado = service.enviar_email_recuperacion(
            destinatario="operador@datamaq.com.ar",
            enlace_restablecimiento="https://datamaq.com.ar/restablecer?token=abc",
        )

        assert resultado is True
        mock_cls.assert_not_called()

    def test_alerta_critica_modo_test_no_conecta_smtp(self, mock_smtp):
        mock_cls, _ = mock_smtp
        service = SmtpEmailService(app_env="test")
        alerta = _crear_alerta()
        disp = _crear_dispositivo()

        resultado = service.notificar_alerta_critica(
            alerta=alerta,
            dispositivo=disp,
            destinatarios=["seguridad@datamaq.com.ar"],
        )

        assert resultado is True
        mock_cls.assert_not_called()

    def test_alerta_critica_sin_destinatarios_retorna_false_incluso_en_test(self, mock_smtp):
        mock_cls, _ = mock_smtp
        service = SmtpEmailService(app_env="test")
        alerta = _crear_alerta()
        disp = _crear_dispositivo()

        resultado = service.notificar_alerta_critica(
            alerta=alerta,
            dispositivo=disp,
            destinatarios=[],
        )

        assert resultado is False
        mock_cls.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Envío de Email de Recuperación y Formato HTML/Texto
# ---------------------------------------------------------------------------


class TestEnvioEmailRecuperacion:
    def test_recuperacion_exitoso_sin_tls_sin_auth(self, mock_smtp):
        mock_cls, mock_server = mock_smtp
        service = SmtpEmailService(
            host="mail.datamaq.com.ar",
            port=25,
            use_tls=False,
            user="",
            password="",
            app_env="production",
        )

        res = service.enviar_email_recuperacion(
            destinatario="juan.perez@empresa.com",
            enlace_restablecimiento="https://app.datamaq.com.ar/token=xyz123",
        )

        assert res is True
        mock_cls.assert_called_once_with(
            "mail.datamaq.com.ar",
            25,
            local_hostname="datamaq.com.ar",
            timeout=10,
        )
        mock_server.ehlo.assert_called_once_with("datamaq.com.ar")
        mock_server.starttls.assert_not_called()
        mock_server.login.assert_not_called()
        mock_server.send_message.assert_called_once()

    def test_recuperacion_exitoso_con_tls_y_auth(self, mock_smtp):
        _, mock_server = mock_smtp
        service = SmtpEmailService(
            host="smtp.gmail.com",
            port=587,
            use_tls=True,
            user="soporte@datamaq.com.ar",
            password="app-password-1234",
            app_env="production",
        )

        res = service.enviar_email_recuperacion(
            destinatario="admin@datamaq.com.ar",
            enlace_restablecimiento="https://app.datamaq.com.ar/restablecer?token=tok-456",
        )

        assert res is True
        mock_server.starttls.assert_called_once()
        # ehlo debe llamarse dos veces: inicial y post-starttls
        assert mock_server.ehlo.call_count == 2
        mock_server.login.assert_called_once_with("soporte@datamaq.com.ar", "app-password-1234")
        mock_server.send_message.assert_called_once()

    def test_recuperacion_usuario_sin_password_no_ejecuta_login(self, mock_smtp):
        _, mock_server = mock_smtp
        service = SmtpEmailService(
            user="usuario_solo",
            password="",
            app_env="production",
        )

        res = service.enviar_email_recuperacion(
            destinatario="test@test.com",
            enlace_restablecimiento="https://link",
        )

        assert res is True
        mock_server.login.assert_not_called()

    def test_formato_completo_email_recuperacion(self, mock_smtp):
        _, mock_server = mock_smtp
        service = SmtpEmailService(
            from_email="no-reply@datamaq.com.ar",
            app_env="production",
        )
        enlace = "https://plataforma.datamaq.com.ar/auth/reset?token=seguro123"

        service.enviar_email_recuperacion(
            destinatario="usuario@datamaq.com.ar",
            enlace_restablecimiento=enlace,
        )

        mensaje_enviado = mock_server.send_message.call_args[0][0]

        # Validaciones de Headers
        assert mensaje_enviado["Subject"] == "Recuperación de contraseña - Datamaq Telemetry"
        assert mensaje_enviado["From"] == "Datamaq Telemetry <no-reply@datamaq.com.ar>"
        assert mensaje_enviado["To"] == "usuario@datamaq.com.ar"
        assert "datamaq.com.ar" in mensaje_enviado["Message-ID"]
        assert mensaje_enviado["X-Mailer"] == "Datamaq Telemetry Mailer 1.0"
        assert mensaje_enviado["Date"] is not None

        # Validación de Cuerpo Texto Plano
        cuerpo_plain = mensaje_enviado.get_body(preferencelist=("plain",)).get_content()
        assert "Estimado usuario," in cuerpo_plain
        assert enlace in cuerpo_plain
        assert "15 minutos" in cuerpo_plain
        assert "El equipo de Soporte y Seguridad de Datamaq Telemetry" in cuerpo_plain

        # Validación de Cuerpo HTML Alternativo
        cuerpo_html = mensaje_enviado.get_body(preferencelist=("html",)).get_content()
        assert "<!DOCTYPE html>" in cuerpo_html
        assert "<html lang='es'>" in cuerpo_html
        assert f"href='{enlace}'" in cuerpo_html
        assert "Restablecer Contraseña" in cuerpo_html
        assert "⚡ Datamaq Telemetry" in cuerpo_html
        assert "15 minutos" in cuerpo_html


# ---------------------------------------------------------------------------
# 4. Envío y Formato de Alertas Críticas
# ---------------------------------------------------------------------------


class TestNotificarAlertaCritica:
    def test_alerta_critica_sin_destinatarios_retorna_false_sin_smtp(self, mock_smtp):
        mock_cls, _ = mock_smtp
        service = SmtpEmailService(app_env="production")
        alerta = _crear_alerta()
        disp = _crear_dispositivo()

        res = service.notificar_alerta_critica(alerta, disp, [])
        assert res is False
        mock_cls.assert_not_called()

    def test_alerta_critica_multiples_destinatarios_exitoso(self, mock_smtp):
        _, mock_server = mock_smtp
        service = SmtpEmailService(
            from_email="alertas@datamaq.com.ar",
            app_env="production",
        )
        alerta = _crear_alerta(tipo_alerta="CORTE_SUMINISTRO")
        disp = _crear_dispositivo(nombre="Generador Diésel #2")
        destinatarios = [
            "guardia@datamaq.com.ar",
            "jefe_planta@datamaq.com.ar",
            "tecnico@datamaq.com.ar",
        ]

        res = service.notificar_alerta_critica(alerta, disp, destinatarios)

        assert res is True
        mock_server.send_message.assert_called_once()
        msg = mock_server.send_message.call_args[0][0]
        assert msg["To"] == "guardia@datamaq.com.ar, jefe_planta@datamaq.com.ar, tecnico@datamaq.com.ar"
        assert "Generador Diésel #2" in msg["Subject"]
        assert "CORTE_SUMINISTRO" in msg["Subject"]


class TestConstruirMensajeAlertaCritica:
    def test_mensaje_alerta_critica_con_todos_los_campos(self):
        disp = _crear_dispositivo(nombre="Torno CNC 01", mac="11:22:33:44:55:66")
        alerta = _crear_alerta(
            tipo_alerta="DESBALANCE_TENSION",
            fase="L2",
            valor_medido=395.5,
            valor_umbral=380.0,
            unidad="V",
            mensaje="Desbalance severo en fase L2 por encima de tolerancia",
            disparada_en=datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc),
        )

        msg = _construir_mensaje_alerta_critica(
            alerta=alerta,
            dispositivo=disp,
            destinatarios=["ops@datamaq.com.ar"],
            from_email="alertas@datamaq.com.ar",
        )

        # Headers
        assert msg["Subject"] == "🚨 [CRÍTICA] Alerta Eléctrica en Torno CNC 01 — DESBALANCE_TENSION"
        assert msg["From"] == "Datamaq Telemetry Alerting <alertas@datamaq.com.ar>"
        assert msg["To"] == "ops@datamaq.com.ar"
        assert msg["Auto-Submitted"] == "auto-generated"
        assert msg["X-Auto-Response-Suppress"] == "All"
        assert msg["Precedence"] == "bulk"
        assert msg["X-Mailer"] == "Datamaq Telemetry Alerting 1.0"
        assert "datamaq.com.ar" in msg["Message-ID"]

        # Plain Text Body
        plain = msg.get_body(preferencelist=("plain",)).get_content()
        assert "ALERTA CRÍTICA DE CALIDAD DE ENERGÍA - DATAMAQ TELEMETRY" in plain
        assert f"Torno CNC 01 ({disp.device_uid.valor})" in plain
        assert "DESBALANCE_TENSION" in plain
        assert "Fase Afectada: L2" in plain
        assert "Valor Medido: 395.5 V" in plain
        assert "Valor Umbral: 380.0 V" in plain
        assert "2026-09-12 14:00:00 UTC" in plain
        assert "Desbalance severo en fase L2 por encima de tolerancia" in plain

        # HTML Body
        html = msg.get_body(preferencelist=("html",)).get_content()
        assert "<!DOCTYPE html><html lang='es'>" in html
        assert "🚨 Alerta Eléctrica Crítica" in html
        assert "Desbalance severo en fase L2" in html
        assert f"Torno CNC 01 ({disp.device_uid.valor})" in html
        assert "395.5 V" in html
        assert "380.0 V" in html
        assert "2026-09-12 14:00:00 UTC" in html

    def test_mensaje_alerta_critica_valores_opcionales_nulos(self):
        disp = _crear_dispositivo(nombre="Bomba Pozo 03")
        alerta = _crear_alerta(
            tipo_alerta="FALLA_COMUNICACION",
            fase=None,
            valor_medido=None,
            valor_umbral=None,
            unidad=None,
            mensaje="Pérdida total de telemetría de dispositivo",
        )

        msg = _construir_mensaje_alerta_critica(
            alerta=alerta,
            dispositivo=disp,
            destinatarios=["ops@datamaq.com.ar"],
            from_email="no-reply@datamaq.com.ar",
        )

        plain = msg.get_body(preferencelist=("plain",)).get_content()
        assert "Fase Afectada: Trifásica / Red" in plain
        assert "Valor Medido: N/A" in plain
        assert "Valor Umbral: N/A" in plain

        html = msg.get_body(preferencelist=("html",)).get_content()
        assert "Trifásica / Red" in html
        assert "N/A" in html

    def test_mensaje_alerta_critica_valor_sin_unidad(self):
        disp = _crear_dispositivo()
        alerta = _crear_alerta(
            tipo_alerta="FACTOR_POTENCIA_BAJO",
            fase="Trifásica",
            valor_medido=0.75,
            valor_umbral=0.85,
            unidad=None,
        )

        msg = _construir_mensaje_alerta_critica(
            alerta=alerta,
            dispositivo=disp,
            destinatarios=["ops@datamaq.com.ar"],
            from_email="no-reply@datamaq.com.ar",
        )

        plain = msg.get_body(preferencelist=("plain",)).get_content()
        assert "Valor Medido: 0.75" in plain
        assert "Valor Umbral: 0.85" in plain
        assert "None" not in plain


# ---------------------------------------------------------------------------
# 5. Manejo Exhaustivo de Excepciones SMTP
# ---------------------------------------------------------------------------


class TestManejoExcepcionesSmtp:
    @pytest.mark.parametrize(
        "excepcion_smtp",
        [
            smtplib.SMTPConnectError(421, b"No se puede conectar al servidor SMTP"),
            smtplib.SMTPAuthenticationError(535, b"Credenciales no validas"),
            smtplib.SMTPServerDisconnected("Conexion cerrada inesperadamente por el servidor"),
            smtplib.SMTPRecipientsRefused({"dest@datamaq.com.ar": (550, b"Buzon no existe")}),
            smtplib.SMTPSenderRefused(553, b"Remitente invalido", "no-reply@datamaq.com.ar"),
            smtplib.SMTPDataError(554, b"Error procesando datos del correo"),
            smtplib.SMTPNotSupportedError("STARTTLS no esta soportado en este puerto"),
            smtplib.SMTPException("Error SMTP generico"),
            TimeoutError("Tiempo de espera agotado al conectar al puerto 25"),
            ConnectionRefusedError("Conexion rechazada"),
            OSError("Red inalcanzable"),
            RuntimeError("Fallo inesperado del sistema"),
        ],
    )
    def test_enviar_smtp_captura_excepciones_y_retorna_false(self, excepcion_smtp):
        service = SmtpEmailService(app_env="production")

        with patch("smtplib.SMTP", side_effect=excepcion_smtp):
            res_recup = service.enviar_email_recuperacion(
                destinatario="usuario@datamaq.com.ar",
                enlace_restablecimiento="https://datamaq.com.ar/restablecer",
            )
            assert res_recup is False

            alerta = _crear_alerta()
            disp = _crear_dispositivo()
            res_alerta = service.notificar_alerta_critica(
                alerta=alerta,
                dispositivo=disp,
                destinatarios=["usuario@datamaq.com.ar"],
            )
            assert res_alerta is False

    def test_fallo_en_send_message_retorna_false(self, mock_smtp):
        _, mock_server = mock_smtp
        mock_server.send_message.side_effect = smtplib.SMTPServerDisconnected("Desconexion durante envio")
        service = SmtpEmailService(app_env="production")

        resultado = service.enviar_email_recuperacion(
            destinatario="admin@datamaq.com.ar",
            enlace_restablecimiento="https://link",
        )
        assert resultado is False

    def test_fallo_en_login_retorna_false(self, mock_smtp):
        _, mock_server = mock_smtp
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failure")
        service = SmtpEmailService(
            user="user",
            password="wrong_password",
            app_env="production",
        )

        resultado = service.enviar_email_recuperacion(
            destinatario="admin@datamaq.com.ar",
            enlace_restablecimiento="https://link",
        )
        assert resultado is False

    def test_fallo_en_starttls_retorna_false(self, mock_smtp):
        _, mock_server = mock_smtp
        mock_server.starttls.side_effect = smtplib.SMTPNotSupportedError("No TLS")
        service = SmtpEmailService(
            use_tls=True,
            app_env="production",
        )

        resultado = service.enviar_email_recuperacion(
            destinatario="admin@datamaq.com.ar",
            enlace_restablecimiento="https://link",
        )
        assert resultado is False


# ---------------------------------------------------------------------------
# 6. Reintentos SMTP (Políticas de Reintento y Resiliencia ante Fallas Transitorias)
# ---------------------------------------------------------------------------


class TestReintentosSmtp:
    def test_reintento_exitoso_tras_fallo_transitorio(self):
        """Simula una política de reintentos donde el 1er intento falla por desconexión

        transitoria del socket y el 2do intento tiene éxito.
        """
        service = SmtpEmailService(app_env="production")

        mock_server_fallido = MagicMock()
        mock_server_fallido.send_message.side_effect = smtplib.SMTPServerDisconnected("Reset temporal")

        mock_server_exitoso = MagicMock()

        intento_actual = 0

        class MockSMTPContext:
            def __init__(self, *args, **kwargs):
                nonlocal intento_actual
                intento_actual += 1

            def __enter__(self):
                if intento_actual == 1:
                    return mock_server_fallido
                return mock_server_exitoso

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

        def enviar_con_politica_reintentos(servicio: SmtpEmailService, max_intentos: int = 3) -> bool:
            for _ in range(max_intentos):
                if servicio.enviar_email_recuperacion("user@datamaq.com.ar", "https://link"):
                    return True
            return False

        with patch("smtplib.SMTP", side_effect=MockSMTPContext):
            resultado = enviar_con_politica_reintentos(service, max_intentos=3)
            assert resultado is True
            assert intento_actual == 2
            mock_server_exitoso.send_message.assert_called_once()

    def test_reintentos_agotados_retorna_false(self):
        """Simula que todos los reintentos fallan por indisponibilidad persistente."""
        service = SmtpEmailService(app_env="production")
        total_intentos = 0

        def smtp_failure(*args, **kwargs):
            nonlocal total_intentos
            total_intentos += 1
            raise smtplib.SMTPConnectError(421, b"Servidor no disponible")

        def enviar_con_politica_reintentos(servicio: SmtpEmailService, max_intentos: int = 3) -> bool:
            for _ in range(max_intentos):
                if servicio.enviar_email_recuperacion("user@datamaq.com.ar", "https://link"):
                    return True
            return False

        with patch("smtplib.SMTP", side_effect=smtp_failure):
            resultado = enviar_con_politica_reintentos(service, max_intentos=3)
            assert resultado is False
            assert total_intentos == 3

    def test_reintento_alerta_critica_exito_al_segundo_intento(self):
        service = SmtpEmailService(app_env="production")
        alerta = _crear_alerta()
        disp = _crear_dispositivo()

        intentos = 0

        def smtp_flaky(*args, **kwargs):
            nonlocal intentos
            intentos += 1
            if intentos == 1:
                raise TimeoutError("Timeout en 1er intento")
            ctx = MagicMock()
            ctx.__enter__.return_value = MagicMock()
            ctx.__exit__.return_value = False
            return ctx

        def notificar_con_reintentos(servicio: SmtpEmailService, max_intentos: int = 2) -> bool:
            for _ in range(max_intentos):
                if servicio.notificar_alerta_critica(alerta, disp, ["admin@datamaq.com.ar"]):
                    return True
            return False

        with patch("smtplib.SMTP", side_effect=smtp_flaky):
            exito = notificar_con_reintentos(service)
            assert exito is True
            assert intentos == 2


# ---------------------------------------------------------------------------
# 7. Variables de Entorno Faltantes, Configuración y Factory Dependencies
# ---------------------------------------------------------------------------


class TestVariablesEntornoYFactoryDependencies:
    def test_get_email_service_singleton_creacion(self):
        service = get_email_service_singleton(
            host="smtp.servidor.com",
            port=465,
            user="usuario_api",
            password="Password123!",
            use_tls=True,
            from_email="notificaciones@datamaq.com.ar",
            app_env="production",
        )
        assert isinstance(service, SmtpEmailService)
        assert service.host == "smtp.servidor.com"
        assert service.port == 465
        assert service.user == "usuario_api"
        assert service.password == "Password123!"
        assert service.use_tls is True
        assert service.from_email == "notificaciones@datamaq.com.ar"
        assert service.app_env == "production"

    def test_get_email_service_con_settings_defaults(self):
        """Verifica que la factory `get_email_service` mapea correctamente

        los campos de Settings cuando las variables opcionales están ausentes/vacías.
        """
        mock_settings = MagicMock(spec=Settings)
        mock_settings.SMTP_HOST = "127.0.0.1"
        mock_settings.SMTP_PORT = 25
        mock_settings.SMTP_USER = ""
        mock_settings.SMTP_PASSWORD = ""
        mock_settings.SMTP_TLS = False
        mock_settings.SMTP_FROM = "no-reply@datamaq.com.ar"
        mock_settings.APP_ENV = "test"

        service = get_email_service(mock_settings)

        assert isinstance(service, SmtpEmailService)
        assert service.host == "127.0.0.1"
        assert service.port == 25
        assert service.user == ""
        assert service.password == ""
        assert service.use_tls is False
        assert service.from_email == "no-reply@datamaq.com.ar"
        assert service.app_env == "test"

    def test_get_email_service_con_settings_personalizados(self):
        mock_settings = MagicMock(spec=Settings)
        mock_settings.SMTP_HOST = "mail.proveedor.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.SMTP_USER = "soporte"
        mock_settings.SMTP_PASSWORD = "SecretoProduccion123!"
        mock_settings.SMTP_TLS = True
        mock_settings.SMTP_FROM = "alertas@datamaq.com.ar"
        mock_settings.APP_ENV = "production"

        service = get_email_service(mock_settings)

        assert service.host == "mail.proveedor.com"
        assert service.port == 587
        assert service.user == "soporte"
        assert service.password == "SecretoProduccion123!"
        assert service.use_tls is True
        assert service.from_email == "alertas@datamaq.com.ar"
        assert service.app_env == "production"

    def test_settings_smtp_valores_por_defecto_sin_variables_en_entorno(self, monkeypatch):
        """Valida que la clase Settings proporcione defaults seguros para SMTP

        cuando no se definen variables de entorno específicas en el sistema.
        """
        claves_smtp = [
            "SMTP_HOST",
            "SMTP_PORT",
            "SMTP_USER",
            "SMTP_PASSWORD",
            "SMTP_TLS",
            "SMTP_FROM",
        ]
        for c in claves_smtp:
            monkeypatch.delenv(c, raising=False)

        settings = Settings(
            _env_file=None,
            APP_ENV="test",
        )

        assert settings.SMTP_HOST == "127.0.0.1"
        assert settings.SMTP_PORT == 25
        assert settings.SMTP_USER == ""
        assert settings.SMTP_PASSWORD == ""
        assert settings.SMTP_TLS is False
        assert settings.SMTP_FROM == "no-reply@datamaq.com.ar"

    def test_mqtt_destinatarios_parsing_con_espacios_y_elementos_vacios(self):
        """Simula la lógica de parseo de destinatarios de alertas utilizada en MqttListener

        cuando la variable de entorno ALERTAS_EMAIL_DESTINATARIOS contiene espacios o vacíos.
        """
        raw_destinatarios = "  alerta1@datamaq.com ,  alerta2@datamaq.com  ,,  alerta3@datamaq.com  "
        dests = [d.strip() for d in raw_destinatarios.split(",") if d.strip()]

        assert dests == [
            "alerta1@datamaq.com",
            "alerta2@datamaq.com",
            "alerta3@datamaq.com",
        ]

        raw_vacio = "   , ,  "
        dests_vacio = [d.strip() for d in raw_vacio.split(",") if d.strip()]
        assert dests_vacio == []

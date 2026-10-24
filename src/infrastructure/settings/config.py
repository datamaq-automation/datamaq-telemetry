"""src/infrastructure/settings/config.py."""

import logging
import os
import secrets
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "datamaq_telemetry"
    DB_POOL_SIZE: int = 4
    DB_MAX_OVERFLOW: int = 8

    # MQTT
    MQTT_BROKER_HOST: str = "127.0.0.1"
    MQTT_BROKER_PORT: int = 8884
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""
    MQTT_CLIENT_ID: str = "datamaq-telemetry-backend"
    MQTT_TOPIC_PREFIX: str = "m/wifi/#,auto24v4m/#"
    MQTT_TLS_ENABLED: bool = False
    MQTT_TLS_CA_CERTS: str = ""
    MQTT_TLS_CERTFILE: str = ""
    MQTT_TLS_KEYFILE: str = ""
    MQTT_MAX_PAYLOAD_BYTES: int = 65536
    MQTT_AUTO_REGISTER_DEVICES: bool = True
    # Sin datos durante este lapso, un dispositivo activo pasa a OFFLINE (#19). 3 x el intervalo normal de 300 s,
    # para no oscilar ONLINE/OFFLINE con un mensaje demorado.
    DISPOSITIVO_OFFLINE_TIMEOUT_S: int = 900
    # Abre además la alerta PÉRDIDA_COMUNICACIÓN. Apagada hasta que el dueño apruebe su texto y su activación.
    DISPOSITIVO_OFFLINE_ALERTA_HABILITADA: bool = False
    MQTT_CLEAN_SESSION: bool = False
    MQTT_RECONNECT_MIN_DELAY_SEG: int = 1
    MQTT_RECONNECT_MAX_DELAY_SEG: int = 60
    MQTT_DEDUP_VENTANA_SEGUNDOS: int = 120
    MQTT_WORKER_MAX_THREADS: int = 2
    MQTT_LOG_LEVEL: str = "WARNING"

    # API
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8885
    API_SECRET_KEY: str = ""
    API_SECRET_KEY_ANTERIOR: str = ""
    # Clave HMAC de los OTP de cambio de contraseña. Dedicada: no reutilizar API_SECRET_KEY.
    OTP_HMAC_KEY: str = ""
    AUTH_TOKEN_EXPIRA_MINUTOS: int = 120
    AUTH_REQUIRED: bool = True
    AUTH_COOKIE_NOMBRE: str = "datamaq_token"
    AUTH_COOKIE_HTTPONLY: bool = True
    AUTH_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "strict"
    APP_ENV: Literal["development", "production", "test"] = "production"
    API_EXPOSE_DOCS: bool | None = None
    DEBUG: bool | None = None
    CORS_ORIGINS: str | None = None
    CSP_HEADER: str = ""
    DEFAULT_USER_PASSWORD: str = "Contraseña123"

    # Rate limiting de login
    LOGIN_MAX_INTENTOS: int = 5
    LOGIN_VENTANA_SEGUNDOS: int = 300

    # Rate limiting 404 para mitigación de escaneos y sondas externas
    RATE_LIMIT_404_MAX_INTENTOS: int = 30
    RATE_LIMIT_404_VENTANA_SEGUNDOS: int = 60

    # SMTP / Email de recuperación
    SMTP_HOST: str = "127.0.0.1"
    SMTP_PORT: int = 25
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = False
    SMTP_FROM: str = "no-reply@datamaq.com.ar"

    FRONTEND_URL: str = "https://www.datamaq.com.ar"
    RECUPERACION_TOKEN_EXPIRA_MINUTOS: int = 15

    # Notificaciones de Alertas Críticas por Email
    ALERTAS_EMAIL_HABILITADAS: bool = True
    ALERTAS_EMAIL_DESTINATARIOS: str = ""
    ALERTAS_EMAIL_COOLDOWN_MINUTOS: int = 30

    # Logging
    LOG_FORMAT: str | None = None  # "console" (clean CLI) o "json" (VPS production)
    LOG_LEVEL: str | None = None

    # Mercado Pago (suscripciones recurrentes / preapproval)
    MP_ACCESS_TOKEN: str = ""
    MP_WEBHOOK_SECRET: str = ""
    MP_BASE_URL: str = "https://api.mercadopago.com"
    MP_BACK_URL_EXITO: str = "https://app.datamaq.com.ar/facturacion?estado=ok"

    # Billing habilitado (D1-D5: 2026-09-24)
    BILLING_HABILITADO: bool = True

    # Energy-ML (descubrimiento de cargas)
    ENERGY_ML_URL: str = "http://127.0.0.1:8100"
    ENERGY_ML_TIMEOUT_S: int = 120

    model_config = SettingsConfigDict(
        env_file=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), ".env"
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("MQTT_TOPIC_PREFIX")
    @classmethod
    def validar_topic_prefix(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("MQTT_TOPIC_PREFIX no puede estar vacío")
        if any(c.isspace() for c in v):
            raise ValueError("MQTT_TOPIC_PREFIX no puede contener espacios")
        subtopicos = [s.strip() for s in v.split(",") if s.strip()]
        for subt in subtopicos:
            niveles = subt.split("/")
            for i, nivel in enumerate(niveles):
                if "#" in nivel:
                    if nivel != "#" or i != len(niveles) - 1:
                        raise ValueError("'#' debe ser el último nivel completo del filtro MQTT")
                elif "+" in nivel and nivel != "+":
                    raise ValueError("'+' debe ocupar un nivel completo del filtro MQTT")
            if "#" not in subt and "+" not in subt:
                raise ValueError("MQTT_TOPIC_PREFIX debe contener al menos un comodín (+ o #)")
        return v

    @model_validator(mode="after")
    def validar_modo_y_postura(self) -> "Settings":
        # Derivación del perfil efectivo (solo campos no especificados, sentinel None)
        if self.DEBUG is None:
            object.__setattr__(self, "DEBUG", self.APP_ENV != "production")
        if self.DEBUG and self.APP_ENV == "production":
            object.__setattr__(self, "APP_ENV", "development")
        es_produccion = self.APP_ENV == "production"

        if self.API_EXPOSE_DOCS is None:
            object.__setattr__(self, "API_EXPOSE_DOCS", not es_produccion)
        if self.CORS_ORIGINS is None:
            object.__setattr__(self, "CORS_ORIGINS", "" if es_produccion else "http://localhost:5173")
        if self.LOG_FORMAT is None:
            object.__setattr__(self, "LOG_FORMAT", "json" if es_produccion else "console")
        if self.LOG_LEVEL is None:
            object.__setattr__(self, "LOG_LEVEL", "INFO" if es_produccion else "DEBUG")

        # Postura de seguridad (sobre DEBUG ya derivado)
        if not self.DEBUG:
            if not self.AUTH_REQUIRED:
                raise ValueError("AUTH_REQUIRED debe ser True en producción")
            if not self.API_SECRET_KEY or self.API_SECRET_KEY == "dev-secret-key-datamaq":
                raise ValueError("API_SECRET_KEY debe ser una clave fuerte en producción")
            if len(self.API_SECRET_KEY) < 16:
                raise ValueError("API_SECRET_KEY debe tener al menos 16 caracteres en producción")
            if not self.DB_PASSWORD or len(self.DB_PASSWORD) < 8:
                raise ValueError("DB_PASSWORD debe tener al menos 8 caracteres en producción")
            if (self.CORS_ORIGINS or "").strip() == "*":
                raise ValueError("CORS_ORIGINS no puede ser '*' en producción")
            # No aborta: la API levanta y el cambio de contraseña responde 503 hasta cargar la clave.
            if not self.otp_hmac_configurada:
                logging.getLogger("settings").critical(
                    "OTP_HMAC_KEY ausente, corta o igual a API_SECRET_KEY: el cambio de contraseña "
                    "responde 503 hasta cargar una clave de al menos 16 caracteres distinta de API_SECRET_KEY"
                )
        elif not self.API_SECRET_KEY:
            object.__setattr__(self, "API_SECRET_KEY", secrets.token_urlsafe(32))
        # Solo desarrollo/test: en producción nunca se genera una clave (quedaría "configurada" con un
        # valor distinto en cada reinicio). Los OTP con clave efímera no sobreviven a un reinicio.
        if self.DEBUG and not self.OTP_HMAC_KEY:
            object.__setattr__(self, "OTP_HMAC_KEY", secrets.token_urlsafe(32))
        # Mismo criterio que OTP: no aborta (un deploy sin el secreto tiraría producción), pero el webhook
        # de MP responde 503 hasta cargarlo. Solo importa si billing está encendido.
        if self.BILLING_HABILITADO and not self.mp_webhook_secret_configurado:
            logging.getLogger("settings").critical(
                "MP_WEBHOOK_SECRET ausente con BILLING_HABILITADO activo: el webhook de Mercado Pago "
                "responde 503 hasta cargar el secreto de la aplicación en MP"
            )
        return self

    @property
    def database_url(self) -> str:
        pwd = f":{self.DB_PASSWORD}" if self.DB_PASSWORD else ""
        return f"mysql+pymysql://{self.DB_USER}{pwd}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

    @property
    def otp_hmac_configurada(self) -> bool:
        """True si la clave OTP es usable: >=16 caracteres y distinta de API_SECRET_KEY."""
        return len(self.OTP_HMAC_KEY) >= 16 and self.OTP_HMAC_KEY != self.API_SECRET_KEY

    @property
    def mp_webhook_secret_configurado(self) -> bool:
        """True si el secreto HMAC del webhook de Mercado Pago es usable (no vacío ni solo espacios)."""
        return bool(self.MP_WEBHOOK_SECRET.strip())

    @property
    def auth_cookie_secure(self) -> bool:
        return not self.DEBUG

    @property
    def auth_cookie_max_age(self) -> int:
        return self.AUTH_TOKEN_EXPIRA_MINUTOS * 60

    @property
    def topic_prefixes(self) -> list[str]:
        return [p.strip() for p in self.MQTT_TOPIC_PREFIX.split(",") if p.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

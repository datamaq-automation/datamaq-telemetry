import os
import secrets
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "datamaq_telemetry"

    # MQTT
    MQTT_BROKER_HOST: str = "127.0.0.1"
    MQTT_BROKER_PORT: int = 8884
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""
    MQTT_CLIENT_ID: str = "datamaq-telemetry-backend"
    MQTT_TOPIC_PREFIX: str = "m/wifi/#"
    MQTT_TLS_ENABLED: bool = False
    MQTT_TLS_CA_CERTS: str = ""
    MQTT_MAX_PAYLOAD_BYTES: int = 65536
    MQTT_AUTO_REGISTER_DEVICES: bool = True

    # API
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8885
    API_SECRET_KEY: str = ""
    API_SECRET_KEY_ANTERIOR: str = ""
    AUTH_TOKEN_EXPIRA_MINUTOS: int = 120
    AUTH_REQUIRED: bool = True
    AUTH_COOKIE_NOMBRE: str = "datamaq_token"
    AUTH_COOKIE_HTTPONLY: bool = True
    AUTH_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "strict"
    API_EXPOSE_DOCS: bool = True
    DEBUG: bool = False
    CORS_ORIGINS: str = ""
    CSP_HEADER: str = ""

    # Rate limiting de login
    LOGIN_MAX_INTENTOS: int = 5
    LOGIN_VENTANA_SEGUNDOS: int = 300

    # Logging
    LOG_FORMAT: str = "console"  # "console" (clean CLI) o "json" (VPS production)
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), ".env"
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validar_postura_seguridad(self) -> "Settings":
        if not self.DEBUG:
            if not self.AUTH_REQUIRED:
                raise ValueError("AUTH_REQUIRED debe ser True en producción")
            if not self.API_SECRET_KEY or self.API_SECRET_KEY == "dev-secret-key-datamaq":
                raise ValueError("API_SECRET_KEY debe ser una clave fuerte en producción")
            if len(self.API_SECRET_KEY) < 16:
                raise ValueError("API_SECRET_KEY debe tener al menos 16 caracteres en producción")
            if not self.DB_PASSWORD or len(self.DB_PASSWORD) < 8:
                raise ValueError("DB_PASSWORD debe tener al menos 8 caracteres en producción")
        elif not self.API_SECRET_KEY:
            object.__setattr__(self, "API_SECRET_KEY", secrets.token_urlsafe(32))
        return self

    @property
    def database_url(self) -> str:
        pwd = f":{self.DB_PASSWORD}" if self.DB_PASSWORD else ""
        return f"mysql+pymysql://{self.DB_USER}{pwd}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

    @property
    def auth_cookie_secure(self) -> bool:
        return not self.DEBUG

    @property
    def auth_cookie_max_age(self) -> int:
        return self.AUTH_TOKEN_EXPIRA_MINUTOS * 60


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

import os
from functools import lru_cache

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

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8885
    API_SECRET_KEY: str = "dev-secret-key-datamaq"
    AUTH_TOKEN_EXPIRA_MINUTOS: int = 480
    DEBUG: bool = True
    CORS_ORIGINS: str = "*"

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

    @property
    def database_url(self) -> str:
        pwd = f":{self.DB_PASSWORD}" if self.DB_PASSWORD else ""
        return f"mysql+pymysql://{self.DB_USER}{pwd}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

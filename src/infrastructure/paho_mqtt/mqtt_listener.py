import json

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.domain.telemetria.ports import PublicadorEventosPort
from src.infrastructure.settings.config import get_settings
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.mysql_repositories import (
    MySQLDispositivosRepository,
    MySQLTelemetriaRepository,
)

logger = get_logger("mqtt_listener")


class MQTTListener:
    def __init__(self, publicador_eventos: PublicadorEventosPort | None = None):
        self.settings = get_settings()
        self.publicador = publicador_eventos
        self.session_factory = get_session_factory()

        self.client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id=self.settings.MQTT_CLIENT_ID,
            clean_session=True,
        )
        if self.settings.MQTT_USERNAME and self.settings.MQTT_PASSWORD:
            self.client.username_pw_set(self.settings.MQTT_USERNAME, self.settings.MQTT_PASSWORD)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.is_running = False

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            logger.info(
                "mqtt_conectado",
                broker_host=self.settings.MQTT_BROKER_HOST,
                broker_port=self.settings.MQTT_BROKER_PORT,
            )
            client.subscribe(self.settings.MQTT_TOPIC_PREFIX, qos=1)
            logger.info("mqtt_suscrito", topico=self.settings.MQTT_TOPIC_PREFIX)
        else:
            logger.error("mqtt_error_conexion", codigo=str(reason_code))

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        logger.warning("mqtt_desconectado", codigo=str(reason_code))

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            raw_text = msg.payload.decode("utf-8")
            payload = json.loads(raw_text) if raw_text else {}
        except Exception as e:
            logger.error("mqtt_payload_invalido", topico=topic, error=str(e))
            return

        db = self.session_factory()
        try:
            repo_disp = MySQLDispositivosRepository(db)
            repo_telem = MySQLTelemetriaRepository(db)
            use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem, self.publicador)
            use_case.ejecutar(topic, payload)
        except Exception as e:
            logger.error("mqtt_error_procesamiento", topico=topic, error=str(e), exc_info=True)
        finally:
            db.close()

    def start(self):
        logger.info("Iniciando MQTTListener en segundo plano...")
        self.is_running = True
        try:
            self.client.connect_async(
                self.settings.MQTT_BROKER_HOST,
                self.settings.MQTT_BROKER_PORT,
                keepalive=60,
            )
            self.client.loop_start()
        except Exception as e:
            logger.warning("No se pudo iniciar conexión MQTT inmediata: %s", e)

    def stop(self):
        logger.info("Deteniendo MQTTListener...")
        self.is_running = False
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

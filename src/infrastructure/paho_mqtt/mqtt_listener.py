"""src/infrastructure/paho_mqtt/mqtt_listener.py."""

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from src.adapters.gateways.dispositivos_datos_maestros_gateway import DispositivosConDatosMaestrosGateway
from src.application.use_cases.gestionar_disponibilidad import GestionarDisponibilidadUseCase
from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.domain.telemetria.ports import PublicadorEventosPort
from src.domain.telemetria.services import FiltroDeduplicacionService
from src.domain.telemetria.servicios.consumo_mqtt import AcumuladorConsumoHorario, uid_desde_topico
from src.infrastructure.paho_mqtt.mqtt_buffer import BufferMensajesMQTT, MensajeBuffer
from src.infrastructure.settings.config import get_settings
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.mysql_repositories import (
    MySQLDispositivosRepository,
    MySQLEventosDisponibilidadRepository,
    MySQLMaquinasRepository,
    MySQLParadasProgramadasRepository,
    MySQLTelemetriaRepository,
)
from src.infrastructure.sqlalchemy.repositories.consumo_mqtt_repository import sumar_consumo
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

logger = get_logger("mqtt_listener")


def _configurar_notificador_alertas(settings, session_factory) -> None:
    from src.application.use_cases.ingesta.procesador_alertas_ingesta import (
        ProcesadorAlertasIngesta,
    )
    from src.infrastructure.auth.email_service import SmtpEmailService
    from src.infrastructure.paho_mqtt.verificador_notificaciones import (
        construir_verificador_notificaciones,
    )

    notificador = SmtpEmailService(
        host=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        user=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
        use_tls=settings.SMTP_TLS,
        from_email=settings.SMTP_FROM,
        app_env=settings.APP_ENV,
    )
    dests = [d.strip() for d in settings.ALERTAS_EMAIL_DESTINATARIOS.split(",") if d.strip()]
    verificador_plan = construir_verificador_notificaciones(
        session_factory, billing_habilitado=settings.BILLING_HABILITADO
    )
    ProcesadorAlertasIngesta.configurar_notificador(notificador, dests, verificador_plan=verificador_plan)


CONSUMO_INTERVALO_S = 60


class MQTTListener:
    def __init__(self, publicador_eventos: PublicadorEventosPort | None = None):
        self.settings = get_settings()
        self.publicador = publicador_eventos
        self.session_factory = get_session_factory()

        self.client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id=self.settings.MQTT_CLIENT_ID,
            clean_session=self.settings.MQTT_CLEAN_SESSION,
        )
        if self.settings.MQTT_USERNAME and self.settings.MQTT_PASSWORD:
            self.client.username_pw_set(self.settings.MQTT_USERNAME, self.settings.MQTT_PASSWORD)

        self.client.reconnect_delay_set(
            min_delay=self.settings.MQTT_RECONNECT_MIN_DELAY_SEG,
            max_delay=self.settings.MQTT_RECONNECT_MAX_DELAY_SEG,
        )

        if self.settings.MQTT_TLS_ENABLED:
            if self.settings.MQTT_TLS_CERTFILE and self.settings.MQTT_TLS_KEYFILE:
                self.client.tls_set(
                    ca_certs=self.settings.MQTT_TLS_CA_CERTS,
                    certfile=self.settings.MQTT_TLS_CERTFILE,
                    keyfile=self.settings.MQTT_TLS_KEYFILE,
                )
            else:
                self.client.tls_set(ca_certs=self.settings.MQTT_TLS_CA_CERTS)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_subscribe = self._on_subscribe
        self.client.on_log = self._on_log

        self._executor = ThreadPoolExecutor(max_workers=self.settings.MQTT_WORKER_MAX_THREADS)
        self._dedup = FiltroDeduplicacionService(self.settings.MQTT_DEDUP_VENTANA_SEGUNDOS)
        self._esta_conectado = False
        self.is_running = False

        self._stop_reintentos = threading.Event()
        self._hilo_reintentos: threading.Thread | None = None
        self._buffer = BufferMensajesMQTT(
            max_size=self.settings.MQTT_BUFFER_MAX_SIZE,
            backoff_base_s=self.settings.MQTT_RETRY_BACKOFF_BASE_S,
            backoff_max_s=self.settings.MQTT_RETRY_BACKOFF_MAX_S,
            on_descarte=self._on_buffer_descarte,
        )
        self._consumo = AcumuladorConsumoHorario()
        self._hilo_consumo: threading.Thread | None = None

        if self.settings.ALERTAS_EMAIL_HABILITADAS:
            _configurar_notificador_alertas(self.settings, self.session_factory)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self._esta_conectado = True
            logger.info(
                "mqtt_conectado",
                broker_host=self.settings.MQTT_BROKER_HOST,
                broker_port=self.settings.MQTT_BROKER_PORT,
            )
            for topico in self.settings.topic_prefixes:
                client.subscribe(topico, qos=1)
                logger.info("mqtt_suscrito", topico=topico)
        else:
            self._esta_conectado = False
            logger.error("mqtt_error_conexion", codigo=str(reason_code))

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self._esta_conectado = False
        logger.warning("mqtt_desconectado", codigo=str(reason_code))
        if reason_code != 0 and self.is_running:
            try:
                client.reconnect()
            except Exception as e:
                logger.warning("mqtt_reconexion_fallida", error=str(e))

    def _on_subscribe(self, client, userdata, mid, granted_qos, properties=None):
        logger.info("mqtt_suscripcion_confirmada", mid=mid, granted_qos=list(granted_qos))
        if any(q == 128 for q in granted_qos):
            logger.error("mqtt_suscripcion_rechazada", mid=mid, granted_qos=list(granted_qos))

    def _on_log(self, client, userdata, level, buf):
        if level == mqtt.MQTT_LOG_ERR:
            logger.error("mqtt_paho_log", mensaje=buf)
        elif level == mqtt.MQTT_LOG_WARNING:
            logger.warning("mqtt_paho_log", mensaje=buf)
        elif level == mqtt.MQTT_LOG_DEBUG:
            logger.debug("mqtt_paho_log", mensaje=buf)
        else:
            logger.info("mqtt_paho_log", mensaje=buf)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        if topic.endswith("/conf/com"):
            # Eco de un comando propio (suscripción a m/wifi/#): ya quedó como mqtt_comando_publicado.
            logger.debug("mqtt_eco_comando_propio_descartado", topico=topic)
            return
        payload_bytes = msg.payload
        if len(payload_bytes) > self.settings.MQTT_MAX_PAYLOAD_BYTES:
            logger.warning("mqtt_payload_descartado", topico=topic, tamano_bytes=len(payload_bytes))
            return

        try:
            raw_text = payload_bytes.decode("utf-8")
            payload = json.loads(raw_text) if raw_text else {}
        except Exception as e:
            logger.error("mqtt_payload_invalido", topico=topic, error=str(e))
            return

        if not isinstance(payload, (dict, list)):
            logger.warning("mqtt_payload_no_dict", topico=topic)
            return

        logger.info("mqtt_mensaje_recibido", topico=topic, tamano_bytes=len(payload_bytes))
        uid = uid_desde_topico(topic)
        if uid:
            self._consumo.registrar(uid, len(payload_bytes), datetime.now(timezone.utc))

        clave_dedup = f"{topic}:{hashlib.sha256(payload_bytes).hexdigest()}"
        if self._dedup.es_duplicado(clave_dedup):
            logger.warning("mqtt_mensaje_duplicado", topico=topic)
            return

        self._executor.submit(self._procesar_mensaje, topic, payload)

    def _on_buffer_descarte(self, descartado: MensajeBuffer) -> None:
        logger.warning(
            "mqtt_buffer_lleno_descarte",
            topico=descartado.topic,
            tamano_maximo=getattr(self.settings, "MQTT_BUFFER_MAX_SIZE", 1000),
            intentos_previos=descartado.intentos,
            timestamp_ingreso=descartado.timestamp_ingreso,
        )

    @property
    def buffer(self) -> BufferMensajesMQTT:
        if not hasattr(self, "_buffer"):
            max_size = getattr(self.settings, "MQTT_BUFFER_MAX_SIZE", 1000)
            backoff_base = getattr(self.settings, "MQTT_RETRY_BACKOFF_BASE_S", 2.0)
            backoff_max = getattr(self.settings, "MQTT_RETRY_BACKOFF_MAX_S", 60.0)
            self._buffer = BufferMensajesMQTT(
                max_size=max_size,
                backoff_base_s=backoff_base,
                backoff_max_s=backoff_max,
                on_descarte=self._on_buffer_descarte,
            )
        return self._buffer

    def _ejecutar_ingesta(self, topic: str, payload: dict | list) -> None:
        """Abre sesión de BD y ejecuta la ingesta correspondiente."""
        db = self.session_factory()
        try:
            repo_disp = DispositivosConDatosMaestrosGateway(
                MySQLDispositivosRepository(db), YamlOrganizacionesRepository()
            )
            repo_telem = MySQLTelemetriaRepository(db)
            disponibilidad_use_case = GestionarDisponibilidadUseCase(
                repo_maquinas=MySQLMaquinasRepository(db),
                repo_eventos=MySQLEventosDisponibilidadRepository(db),
                repo_paradas=MySQLParadasProgramadasRepository(db),
            )

            if topic.startswith("auto24v4m/"):
                from src.application.use_cases.ingesta.ingestar_automate import IngestarAutomateUseCase

                automate_use_case = IngestarAutomateUseCase(
                    repo_dispositivos=repo_disp,
                    disponibilidad_use_case=disponibilidad_use_case,
                    logger=logger,
                    permitir_auto_registro=self.settings.MQTT_AUTO_REGISTER_DEVICES,
                )
                automate_use_case.ejecutar(topic, payload)
            elif isinstance(payload, dict):
                use_case = IngestarTelemetriaUseCase(
                    repo_dispositivos=repo_disp,
                    repo_telemetria=repo_telem,
                    publicador=self.publicador,
                    logger=logger,
                    permitir_auto_registro=self.settings.MQTT_AUTO_REGISTER_DEVICES,
                    disponibilidad_use_case=disponibilidad_use_case,
                )
                use_case.ejecutar(topic, payload)
        finally:
            db.close()

    def _procesar_mensaje(self, topic: str, payload: dict | list) -> None:
        try:
            self._ejecutar_ingesta(topic, payload)
        except Exception as e:
            logger.error("mqtt_error_procesamiento", topico=topic, error=str(e), exc_info=True)
            self.buffer.encolar(topic, payload, error=str(e))
            logger.warning(
                "mqtt_mensaje_encolado_buffer",
                topico=topic,
                tamano_buffer=len(self.buffer),
                error=str(e),
            )

    def _bucle_consumo(self) -> None:
        """Vuelca a la base el consumo MQTT por hora cada CONSUMO_INTERVALO_S (#93), fuera del camino de ingesta."""
        while not self._stop_reintentos.wait(timeout=CONSUMO_INTERVALO_S):
            self.persistir_consumo()

    def persistir_consumo(self) -> None:
        datos = self._consumo.extraer()
        if not datos:
            return
        try:
            sumar_consumo(self.session_factory, datos)
        except Exception as e:
            self._consumo.fusionar(datos)
            logger.warning("mqtt_consumo_persistencia_fallida", error=str(e))

    def _bucle_reintentos(self) -> None:
        """Hilo de fondo que reintenta periódicamente los mensajes encolados en el buffer."""
        stop_ev = getattr(self, "_stop_reintentos", None)
        while stop_ev is not None and not stop_ev.wait(timeout=1.0):
            if len(self.buffer) > 0:
                try:
                    recuperados = self.buffer.procesar_pendientes(self._ejecutar_ingesta)
                    if recuperados > 0:
                        logger.info(
                            "mqtt_buffer_mensajes_recuperados",
                            recuperados=recuperados,
                            restantes=len(self.buffer),
                        )
                except Exception as e:
                    logger.debug("mqtt_buffer_reintento_fallido", error=str(e))

    def procesar_buffer_pendiente(self, ignorar_backoff: bool = True) -> int:
        """Fuerza el reprocesamiento inmediato de los mensajes en el buffer."""
        return self.buffer.procesar_pendientes(self._ejecutar_ingesta, ignorar_backoff=ignorar_backoff)

    def esta_conectado(self) -> bool:
        return self._esta_conectado

    def publicar_comando(self, topico: str, payload: dict) -> bool:
        if not self._esta_conectado:
            logger.warning("mqtt_comando_no_enviado_desconectado", topico=topico)
            return False
        try:
            payload_str = json.dumps(payload)
            self.client.publish(topico, payload_str, qos=1)
            logger.info("mqtt_comando_publicado", topico=topico, payload=payload)
            return True
        except Exception as e:
            logger.error("mqtt_error_publicar_comando", topico=topico, error=str(e))
            return False

    def activar_tiempo_real_dispositivo(self, device_uid: str, segundos: int = 120) -> bool:
        """Envía el comando nativo realtime_sync_mode al medidor físico por MQTT."""
        uid_limpio = device_uid.replace(":", "").replace("-", "").upper()
        topico = f"m/wifi/{uid_limpio}/conf/com"
        correlator = int(time.time())
        comando = {
            "correlatorid": correlator,
            "set": "realtime_sync_mode",
            "payload": {"time_s": segundos},
        }
        return self.publicar_comando(topico, comando)

    def start(self):
        logger.info("iniciando_mqtt_listener")
        self.is_running = True
        if hasattr(self, "_stop_reintentos"):
            self._stop_reintentos.clear()
            self._hilo_reintentos = threading.Thread(
                target=self._bucle_reintentos,
                name="mqtt-buffer-retry",
                daemon=True,
            )
            self._hilo_reintentos.start()
            self._hilo_consumo = threading.Thread(
                target=self._bucle_consumo,
                name="mqtt-consumo-horario",
                daemon=True,
            )
            self._hilo_consumo.start()

        try:
            self.client.connect_async(
                self.settings.MQTT_BROKER_HOST,
                self.settings.MQTT_BROKER_PORT,
                keepalive=60,
            )
            self.client.loop_start()
        except Exception as e:
            logger.warning("mqtt_conexion_inmediata_fallida", error=str(e))

    def stop(self):
        logger.info("deteniendo_mqtt_listener")
        self.is_running = False
        if hasattr(self, "_stop_reintentos"):
            self._stop_reintentos.set()
            if self._hilo_reintentos and self._hilo_reintentos.is_alive():
                self._hilo_reintentos.join(timeout=2.0)

        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass
        self._executor.shutdown(wait=True)
        self.persistir_consumo()

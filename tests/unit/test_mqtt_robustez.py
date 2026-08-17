"""Spec G — Robustez del Listener MQTT (hardening de ingesta)."""

import threading
from datetime import datetime, timedelta, timezone

import pydantic
import pytest

from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.domain.telemetria.services import FiltroDeduplicacionService
from src.infrastructure.paho_mqtt import mqtt_listener
from src.infrastructure.paho_mqtt.mqtt_listener import MQTTListener
from src.infrastructure.settings.config import Settings


class _Msg:
    def __init__(self, topic: str, payload: bytes):
        self.topic = topic
        self.payload = payload


class _LoggerFake:
    def __init__(self):
        self.eventos: list[tuple[str, dict]] = []

    def info(self, evento: str, **kwargs: object) -> None:
        self.eventos.append((evento, dict(kwargs)))

    def warning(self, evento: str, **kwargs: object) -> None:
        self.eventos.append((evento, dict(kwargs)))

    def error(self, evento: str, **kwargs: object) -> None:
        self.eventos.append((evento, dict(kwargs)))

    def debug(self, evento: str, **kwargs: object) -> None:
        self.eventos.append((evento, dict(kwargs)))


class _FakeClient:
    """Cliente paho falso que registra las llamadas de configuración."""

    def __init__(self, *args, **kwargs):
        self.clean_session = kwargs.get("clean_session")
        self.tls_kwargs: dict = {}
        self.reconnect_delay: tuple | None = None
        self.reconectado = False
        self.suscrito: list[tuple] = []
        self.loop_stop_called = False
        self.disconnect_called = False

    def username_pw_set(self, usuario: str, contrasena: str) -> None:
        pass

    def tls_set(self, *args, **kwargs) -> None:
        self.tls_kwargs = kwargs

    def reconnect_delay_set(self, min_delay: int = 1, max_delay: int = 120) -> None:
        self.reconnect_delay = (min_delay, max_delay)

    def reconnect(self) -> None:
        self.reconectado = True

    def subscribe(self, topico: str, qos: int = 0) -> None:
        self.suscrito.append((topico, qos))

    def loop_stop(self) -> None:
        self.loop_stop_called = True

    def disconnect(self) -> None:
        self.disconnect_called = True

    def connect_async(self, host: str, port: int, keepalive: int = 60) -> None:
        pass

    def loop_start(self) -> None:
        pass


class _FakeExecutor:
    """Executor determinista que captura tareas sin ejecutarlas."""

    def __init__(self):
        self.tareas: list[tuple] = []
        self.shutdown_wait: bool | None = None

    def submit(self, fn, *args, **kwargs):
        self.tareas.append((fn, args))
        return None

    def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
        self.shutdown_wait = wait


class _DBSessionStub:
    def close(self) -> None:
        pass


def _listener(monkeypatch, settings: Settings, logger_fake: _LoggerFake) -> MQTTListener:
    """Construye un listener sin ejecutar __init__ (estado mínimo inyectado)."""
    monkeypatch.setattr(mqtt_listener, "logger", logger_fake)
    listener = MQTTListener.__new__(MQTTListener)
    listener.settings = settings
    listener.session_factory = lambda: _DBSessionStub()
    listener.publicador = None
    listener.client = _FakeClient()
    listener.is_running = False
    listener._esta_conectado = False
    listener._executor = _FakeExecutor()
    listener._dedup = FiltroDeduplicacionService(settings.MQTT_DEDUP_VENTANA_SEGUNDOS)
    return listener


# ---------------------------------------------------------------------------
# Filtro de deduplicación (dominio)
# ---------------------------------------------------------------------------


def test_deduplicacion_descarta_duplicado_dentro_ventana():
    filtro = FiltroDeduplicacionService(ventana_segundos=120)
    assert filtro.es_duplicado("clave-a") is False
    assert filtro.es_duplicado("clave-a") is True


def test_deduplicacion_permite_tras_vencer_ventana():
    filtro = FiltroDeduplicacionService(ventana_segundos=120)
    ahora = datetime.now(timezone.utc)
    assert filtro.es_duplicado("clave-a", ahora=ahora) is False
    futuro = ahora + timedelta(seconds=121)
    assert filtro.es_duplicado("clave-a", ahora=futuro) is False


def test_deduplicacion_clave_distinta_no_duplica():
    filtro = FiltroDeduplicacionService(ventana_segundos=120)
    assert filtro.es_duplicado("m/wifi/AAA/inst") is False
    assert filtro.es_duplicado("m/wifi/BBB/inst") is False


def test_deduplicacion_poda_entradas_vencidas():
    filtro = FiltroDeduplicacionService(ventana_segundos=120)
    ahora = datetime.now(timezone.utc)
    filtro.es_duplicado("clave-a", ahora=ahora)
    futuro = ahora + timedelta(seconds=121)
    # Una llamada con otra clave dispara la poda de las entradas vencidas.
    filtro.es_duplicado("clave-b", ahora=futuro)
    assert "clave-a" not in filtro._vistos
    assert "clave-b" in filtro._vistos


def test_deduplicacion_limpiar_vacia_registro():
    filtro = FiltroDeduplicacionService(ventana_segundos=120)
    filtro.es_duplicado("clave-a")
    assert "clave-a" in filtro._vistos

    filtro.limpiar()

    assert filtro._vistos == {}


# ---------------------------------------------------------------------------
# Encolado en workers (H1)
# ---------------------------------------------------------------------------


def test_on_message_encola_y_retorna(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True, MQTT_MAX_PAYLOAD_BYTES=10000)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    session_abierta = []

    def _factory():
        session_abierta.append(True)
        return _DBSessionStub()

    listener.session_factory = _factory

    listener._on_message(None, None, _Msg("m/wifi/AABBCCDDEEFF/inst", b'{"x": 1}'))

    # La sesión DB NO debe abrirse en el callback síncrono: solo se encola.
    assert session_abierta == []
    assert len(listener._executor.tareas) == 1
    assert listener._executor.tareas[0][1] == ("m/wifi/AABBCCDDEEFF/inst", {"x": 1})


def test_worker_procesa_mensaje_encolado(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True, MQTT_MAX_PAYLOAD_BYTES=10000)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    ejecutados: list[tuple] = []

    class _UseCaseFake:
        def __init__(self, **kwargs):
            pass

        def ejecutar(self, topico: str, payload: dict) -> None:
            ejecutados.append((topico, payload))

    monkeypatch.setattr(mqtt_listener, "MySQLDispositivosRepository", lambda db: None)
    monkeypatch.setattr(mqtt_listener, "MySQLTelemetriaRepository", lambda db: None)
    monkeypatch.setattr(mqtt_listener, "IngestarTelemetriaUseCase", _UseCaseFake)

    listener._procesar_mensaje("m/wifi/AABBCCDDEEFF/inst", {"x": 1})

    assert ejecutados == [("m/wifi/AABBCCDDEEFF/inst", {"x": 1})]


def test_stop_apaga_executor(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    listener.stop()

    assert listener.client.loop_stop_called is True
    assert listener.client.disconnect_called is True
    assert listener._executor.shutdown_wait is True
    assert listener.is_running is False


# ---------------------------------------------------------------------------
# Validación de payload (H5)
# ---------------------------------------------------------------------------


def test_payload_json_lista_descartado(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True, MQTT_MAX_PAYLOAD_BYTES=10000)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    listener._on_message(None, None, _Msg("m/wifi/AABBCCDDEEFF/inst", b"[1, 2, 3]"))

    assert any(e[0] == "mqtt_payload_no_dict" for e in logger_fake.eventos)


def test_payload_json_string_descartado(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True, MQTT_MAX_PAYLOAD_BYTES=10000)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    listener._on_message(None, None, _Msg("m/wifi/AABBCCDDEEFF/inst", b'"hola"'))

    assert any(e[0] == "mqtt_payload_no_dict" for e in logger_fake.eventos)


def test_payload_vacio_procesado(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True, MQTT_MAX_PAYLOAD_BYTES=10000)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    listener._on_message(None, None, _Msg("m/wifi/AABBCCDDEEFF/inst", b""))

    assert not any(e[0] == "mqtt_payload_no_dict" for e in logger_fake.eventos)


# ---------------------------------------------------------------------------
# Reconexión y sesión (H2, H4)
# ---------------------------------------------------------------------------


def test_init_configura_reconnect_delay_set(monkeypatch):
    monkeypatch.setattr(mqtt_listener.mqtt, "Client", _FakeClient)
    monkeypatch.setattr(
        mqtt_listener,
        "get_settings",
        lambda: Settings(_env_file=None, DEBUG=True),
    )
    monkeypatch.setattr(mqtt_listener, "get_session_factory", lambda: _DBSessionStub())

    listener = MQTTListener()

    assert listener.client.reconnect_delay == (1, 60)


def test_on_disconnect_rc_no_cero_reconecta(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)
    listener.is_running = True

    listener._on_disconnect(listener.client, None, None, 1, None)

    assert listener.client.reconectado is True


def test_on_disconnect_rc_cero_no_reconecta(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)
    listener.is_running = True

    listener._on_disconnect(listener.client, None, None, 0, None)

    assert listener.client.reconectado is False


def test_client_clean_session_false(monkeypatch):
    monkeypatch.setattr(mqtt_listener.mqtt, "Client", _FakeClient)
    monkeypatch.setattr(
        mqtt_listener,
        "get_settings",
        lambda: Settings(_env_file=None, DEBUG=True),
    )
    monkeypatch.setattr(mqtt_listener, "get_session_factory", lambda: _DBSessionStub())

    listener = MQTTListener()

    assert listener.client.clean_session is False


# ---------------------------------------------------------------------------
# Observabilidad y estado (H6, H8)
# ---------------------------------------------------------------------------


def test_on_subscribe_logea_grants(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    listener._on_subscribe(listener.client, None, 1, [1])

    assert any(e[0] == "mqtt_suscripcion_confirmada" for e in logger_fake.eventos)


def test_on_subscribe_qos_128_logea_error(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    listener._on_subscribe(listener.client, None, 1, [128])

    assert any(e[0] == "mqtt_suscripcion_rechazada" for e in logger_fake.eventos)


def test_esta_conectado_true_tras_on_connect(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    listener._on_connect(listener.client, None, None, 0, None)

    assert listener.esta_conectado() is True


def test_esta_conectado_false_tras_on_disconnect(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)
    listener._esta_conectado = True

    listener._on_disconnect(listener.client, None, None, 1, None)

    assert listener.esta_conectado() is False


# ---------------------------------------------------------------------------
# Configuración (H7)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "topico_invalido",
    ["m/wifi", "m/#/x", "m wifi/#", "", "#x", "m/wifi/#/extra"],
)
def test_topic_prefix_invalido_rechazado(topico_invalido):
    with pytest.raises(pydantic.ValidationError):
        Settings(_env_file=None, DEBUG=True, MQTT_TOPIC_PREFIX=topico_invalido)


@pytest.mark.parametrize("topico_valido", ["m/wifi/#", "m/+/#", "m/wifi/+/inst", "#"])
def test_topic_prefix_valido_aceptado(topico_valido):
    settings = Settings(_env_file=None, DEBUG=True, MQTT_TOPIC_PREFIX=topico_valido)
    assert settings.MQTT_TOPIC_PREFIX == topico_valido


def test_defaults_robustez_mqtt():
    assert Settings.model_fields["MQTT_CLEAN_SESSION"].default is False
    assert Settings.model_fields["MQTT_RECONNECT_MIN_DELAY_SEG"].default == 1
    assert Settings.model_fields["MQTT_RECONNECT_MAX_DELAY_SEG"].default == 60
    assert Settings.model_fields["MQTT_DEDUP_VENTANA_SEGUNDOS"].default == 120
    assert Settings.model_fields["MQTT_WORKER_MAX_THREADS"].default == 2
    assert Settings.model_fields["DB_POOL_SIZE"].default == 4
    assert Settings.model_fields["DB_MAX_OVERFLOW"].default == 8


# ---------------------------------------------------------------------------
# mTLS (H9)
# ---------------------------------------------------------------------------


def test_tls_mutuo_cuando_certfile_configurado(monkeypatch):
    monkeypatch.setattr(mqtt_listener.mqtt, "Client", _FakeClient)
    monkeypatch.setattr(
        mqtt_listener,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            DEBUG=True,
            MQTT_TLS_ENABLED=True,
            MQTT_TLS_CA_CERTS="/ca.pem",
            MQTT_TLS_CERTFILE="/client.crt",
            MQTT_TLS_KEYFILE="/client.key",
        ),
    )
    monkeypatch.setattr(mqtt_listener, "get_session_factory", lambda: _DBSessionStub())

    listener = MQTTListener()

    assert listener.client.tls_kwargs.get("certfile") == "/client.crt"
    assert listener.client.tls_kwargs.get("keyfile") == "/client.key"


# ---------------------------------------------------------------------------
# Concurrencia use case (H1 derivado)
# ---------------------------------------------------------------------------


def test_use_case_cache_lock():
    IngestarTelemetriaUseCase._device_cache.clear()
    IngestarTelemetriaUseCase._ultimos_heartbeats.clear()
    IngestarTelemetriaUseCase._ultimas_persistencias.clear()

    lock = getattr(IngestarTelemetriaUseCase, "_lock", None)
    assert isinstance(lock, type(threading.Lock()))


# ---------------------------------------------------------------------------
# Cobertura de ramas del listener (observabilidad, errores y ciclo de vida)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nivel,evento_esperado",
    [
        (mqtt_listener.mqtt.MQTT_LOG_ERR, "mqtt_paho_log"),
        (mqtt_listener.mqtt.MQTT_LOG_WARNING, "mqtt_paho_log"),
        (mqtt_listener.mqtt.MQTT_LOG_DEBUG, "mqtt_paho_log"),
        (mqtt_listener.mqtt.MQTT_LOG_INFO, "mqtt_paho_log"),
    ],
)
def test_on_log_mapea_niveles(monkeypatch, nivel, evento_esperado):
    settings = Settings(_env_file=None, DEBUG=True)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    listener._on_log(listener.client, None, nivel, "mensaje")

    assert any(e[0] == evento_esperado for e in logger_fake.eventos)


def test_on_connect_rc_no_cero_apaga_flag(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)
    listener._esta_conectado = True

    listener._on_connect(listener.client, None, None, 5, None)

    assert listener.esta_conectado() is False
    assert any(e[0] == "mqtt_error_conexion" for e in logger_fake.eventos)


def test_on_disconnect_reconexion_fallida(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)
    listener.is_running = True

    class _ClientQueFalla(_FakeClient):
        def reconnect(self) -> None:
            raise RuntimeError("boom")

    listener.client = _ClientQueFalla()

    listener._on_disconnect(listener.client, None, None, 1, None)

    assert any(e[0] == "mqtt_reconexion_fallida" for e in logger_fake.eventos)


def test_on_message_payload_invalido_logea(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True, MQTT_MAX_PAYLOAD_BYTES=10000)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    listener._on_message(None, None, _Msg("m/wifi/AABBCCDDEEFF/inst", b"\xff\xfe{no-json"))

    assert any(e[0] == "mqtt_payload_invalido" for e in logger_fake.eventos)
    assert listener._executor.tareas == []


def test_on_message_duplicado_descartado(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True, MQTT_MAX_PAYLOAD_BYTES=10000)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    payload = b'{"x": 1}'
    msg = _Msg("m/wifi/AABBCCDDEEFF/inst", payload)
    listener._on_message(None, None, msg)
    listener._on_message(None, None, msg)

    assert len(listener._executor.tareas) == 1
    assert any(e[0] == "mqtt_mensaje_duplicado" for e in logger_fake.eventos)


def test_on_message_oversize_descartado(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True, MQTT_MAX_PAYLOAD_BYTES=8)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    listener._on_message(None, None, _Msg("m/wifi/AABBCCDDEEFF/inst", b"123456789"))

    assert any(e[0] == "mqtt_payload_descartado" for e in logger_fake.eventos)
    assert listener._executor.tareas == []


def test_worker_procesa_mensaje_error_registrado(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    class _UseCaseQueFalla:
        def __init__(self, **kwargs):
            pass

        def ejecutar(self, topico: str, payload: dict) -> None:
            raise RuntimeError("fallo")

    monkeypatch.setattr(mqtt_listener, "MySQLDispositivosRepository", lambda db: None)
    monkeypatch.setattr(mqtt_listener, "MySQLTelemetriaRepository", lambda db: None)
    monkeypatch.setattr(mqtt_listener, "IngestarTelemetriaUseCase", _UseCaseQueFalla)

    listener._procesar_mensaje("m/wifi/AABBCCDDEEFF/inst", {"x": 1})

    assert any(e[0] == "mqtt_error_procesamiento" for e in logger_fake.eventos)


def test_start_conecta_y_arranca_loop(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    listener.start()

    assert listener.is_running is True


def test_start_excepcion_manejada(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    class _ClientQueFalla(_FakeClient):
        def connect_async(self, host: str, port: int, keepalive: int = 60) -> None:
            raise RuntimeError("sin red")

    listener.client = _ClientQueFalla()

    listener.start()

    assert any(e[0] == "mqtt_conexion_inmediata_fallida" for e in logger_fake.eventos)
    assert listener.is_running is True


def test_stop_excepcion_manejada(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    class _ClientQueFalla(_FakeClient):
        def loop_stop(self) -> None:
            raise RuntimeError("loop detenido")

    listener.client = _ClientQueFalla()

    listener.stop()

    assert listener._executor.shutdown_wait is True
    assert listener.is_running is False


def test_init_con_credenciales_llama_username_pw_set(monkeypatch):
    llamadas: list[tuple] = []

    class _ClientConCredenciales(_FakeClient):
        def username_pw_set(self, usuario: str, contrasena: str) -> None:
            llamadas.append((usuario, contrasena))

    monkeypatch.setattr(mqtt_listener.mqtt, "Client", _ClientConCredenciales)
    monkeypatch.setattr(
        mqtt_listener,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            DEBUG=True,
            MQTT_USERNAME="user",
            MQTT_PASSWORD="pass",
        ),
    )
    monkeypatch.setattr(mqtt_listener, "get_session_factory", lambda: _DBSessionStub())

    MQTTListener()

    assert llamadas == [("user", "pass")]

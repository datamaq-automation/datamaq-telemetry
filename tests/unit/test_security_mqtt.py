"""tests/unit/test_security_mqtt.py — Endurecimiento MQTT: TLS, límite de payload, auto-registro y logs."""

from unittest.mock import MagicMock

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
    def __init__(self, *args, **kwargs):
        self.tls_called = False

    def username_pw_set(self, usuario: str, contrasena: str) -> None:
        pass

    def reconnect_delay_set(self, min_delay: int = 1, max_delay: int = 120) -> None:
        pass

    def tls_set(self, *args, **kwargs) -> None:
        self.tls_called = True


class _DBSessionStub:
    def close(self) -> None:
        pass


class _FakeExecutor:
    def submit(self, fn, *args, **kwargs):
        return None

    def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
        pass


def _listener(monkeypatch, settings: Settings, logger_fake: _LoggerFake) -> MQTTListener:
    monkeypatch.setattr(mqtt_listener, "logger", logger_fake)
    listener = MQTTListener.__new__(MQTTListener)
    listener.settings = settings
    listener.session_factory = lambda: _DBSessionStub()
    listener.publicador = None
    listener._executor = _FakeExecutor()
    listener._dedup = FiltroDeduplicacionService(settings.MQTT_DEDUP_VENTANA_SEGUNDOS)
    return listener


def test_listener_descarta_payload_grande(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True, MQTT_MAX_PAYLOAD_BYTES=100)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    listener._on_message(None, None, _Msg("m/wifi/D48C49F03564/inst", b"x" * 200))

    assert any(e[0] == "mqtt_payload_descartado" for e in logger_fake.eventos)


def test_log_debug_sin_payload(monkeypatch):
    settings = Settings(_env_file=None, DEBUG=True, MQTT_MAX_PAYLOAD_BYTES=10000)
    logger_fake = _LoggerFake()
    listener = _listener(monkeypatch, settings, logger_fake)

    listener._on_message(None, None, _Msg("a/b", b'{"x": 1}'))

    debug = [e for e in logger_fake.eventos if e[0] == "mqtt_mensaje_recibido"]
    assert len(debug) == 1
    assert "payload" not in debug[0][1]


def test_tls_configurado_cuando_habilitado(monkeypatch):
    monkeypatch.setattr(mqtt_listener.mqtt, "Client", _FakeClient)
    monkeypatch.setattr(
        mqtt_listener,
        "get_settings",
        lambda: Settings(_env_file=None, DEBUG=True, MQTT_TLS_ENABLED=True, MQTT_TLS_CA_CERTS="/ca.pem"),
    )
    monkeypatch.setattr(mqtt_listener, "get_session_factory", lambda: _DBSessionStub())

    listener = MQTTListener()

    assert listener.client.tls_called is True


def test_sin_auto_registro_descarta_mac_desconocida():
    IngestarTelemetriaUseCase.limpiar_estado()

    repo_disp = MagicMock()
    repo_disp.obtener_por_uid.return_value = None
    repo_telem = MagicMock()

    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem, permitir_auto_registro=False)

    use_case.ejecutar("m/wifi/AABBCCDDEEFF/inst", {"timestamp": 1767377818, "phase_r": {"voltage_V": 226.9}})

    repo_disp.guardar.assert_not_called()
    repo_telem.guardar_instantanea.assert_not_called()

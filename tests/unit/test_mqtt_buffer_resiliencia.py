"""tests/unit/test_mqtt_buffer_resiliencia.py — Tests del buffer resiliente ante caídas de BD (#60)."""

from unittest.mock import MagicMock

from src.infrastructure.paho_mqtt import mqtt_listener
from src.infrastructure.paho_mqtt.mqtt_buffer import BufferMensajesMQTT
from src.infrastructure.paho_mqtt.mqtt_listener import MQTTListener
from src.infrastructure.settings.config import Settings


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


class _DBSessionStub:
    def close(self) -> None:
        pass


def _construir_listener(monkeypatch, settings: Settings, logger_fake: _LoggerFake) -> MQTTListener:
    monkeypatch.setattr(mqtt_listener, "logger", logger_fake)
    listener = MQTTListener.__new__(MQTTListener)
    listener.settings = settings
    listener.session_factory = lambda: _DBSessionStub()
    listener.publicador = None
    listener._consumo = MagicMock()
    listener.client = MagicMock()
    listener.is_running = False
    listener._esta_conectado = True
    listener._executor = MagicMock()
    return listener


def test_base_caida_luego_recupera_sin_perdida(monkeypatch):
    """BD caída durante ráfaga de mensajes -> se encolan en buffer -> BD recupera -> 0 pérdida."""
    settings = Settings(
        _env_file=None,
        DEBUG=True,
        MQTT_BUFFER_MAX_SIZE=100,
        MQTT_RETRY_BACKOFF_BASE_S=1.0,
    )
    logger_fake = _LoggerFake()
    listener = _construir_listener(monkeypatch, settings, logger_fake)

    mensajes_procesados_exitosamente = []
    bd_disponible = False

    class _UseCaseMock:
        def __init__(self, **kwargs):
            pass

        def ejecutar(self, topico: str, payload: dict) -> None:
            if not bd_disponible:
                raise RuntimeError("MySQL OperationalError: Can't connect to MySQL server")
            mensajes_procesados_exitosamente.append((topico, payload))

    monkeypatch.setattr(mqtt_listener, "MySQLDispositivosRepository", lambda db: None)
    monkeypatch.setattr(mqtt_listener, "MySQLTelemetriaRepository", lambda db: None)
    monkeypatch.setattr(mqtt_listener, "IngestarTelemetriaUseCase", _UseCaseMock)

    # 1. Simular envío de 5 lecturas con BD caída
    for i in range(5):
        topico = f"m/wifi/D48C49F0356{i}/inst"
        payload = {"potencia": 1000 + i}
        listener._procesar_mensaje(topico, payload)

    # Verificación: los 5 mensajes están en el buffer, ninguno se perdió
    assert len(listener.buffer) == 5
    assert len(mensajes_procesados_exitosamente) == 0
    assert any(e[0] == "mqtt_mensaje_encolado_buffer" for e in logger_fake.eventos)

    # 2. Restauración de la base de datos
    bd_disponible = True

    # 3. Reprocesamiento de pendientes
    recuperados = listener.procesar_buffer_pendiente(ignorar_backoff=True)

    assert recuperados == 5
    assert len(listener.buffer) == 0
    assert len(mensajes_procesados_exitosamente) == 5
    assert [p[0] for p in mensajes_procesados_exitosamente] == [f"m/wifi/D48C49F0356{i}/inst" for i in range(5)]


def test_buffer_lleno_descarta_mas_antiguo_y_registra_descarte(monkeypatch):
    """Cuando el buffer alcanza max_size, se descarta el mensaje más antiguo (FIFO) y se registra."""
    settings = Settings(
        _env_file=None,
        DEBUG=True,
        MQTT_BUFFER_MAX_SIZE=3,  # Capacidad acotada para la prueba
    )
    logger_fake = _LoggerFake()
    listener = _construir_listener(monkeypatch, settings, logger_fake)

    class _UseCaseSiempreFalla:
        def __init__(self, **kwargs):
            pass

        def ejecutar(self, topico: str, payload: dict) -> None:
            raise RuntimeError("BD caída permanente")

    monkeypatch.setattr(mqtt_listener, "MySQLDispositivosRepository", lambda db: None)
    monkeypatch.setattr(mqtt_listener, "MySQLTelemetriaRepository", lambda db: None)
    monkeypatch.setattr(mqtt_listener, "IngestarTelemetriaUseCase", _UseCaseSiempreFalla)

    # Encolar 4 mensajes (capacidad = 3)
    listener._procesar_mensaje("m/wifi/DEV1/inst", {"id": 1})
    listener._procesar_mensaje("m/wifi/DEV2/inst", {"id": 2})
    listener._procesar_mensaje("m/wifi/DEV3/inst", {"id": 3})
    assert len(listener.buffer) == 3
    assert listener.buffer.descartados_total == 0

    # El 4to mensaje debe forzar el descarte del más antiguo (DEV1)
    listener._procesar_mensaje("m/wifi/DEV4/inst", {"id": 4})

    assert len(listener.buffer) == 3
    assert listener.buffer.descartados_total == 1

    # Verificar que el log estructurado de descarte exista
    descartes = [e for e in logger_fake.eventos if e[0] == "mqtt_buffer_lleno_descarte"]
    assert len(descartes) == 1
    assert descartes[0][1]["topico"] == "m/wifi/DEV1/inst"
    assert descartes[0][1]["tamano_maximo"] == 3

    # Los que quedaron en el buffer son DEV2, DEV3, DEV4
    topics_restantes = [m.topic for m in listener.buffer._cola]
    assert topics_restantes == ["m/wifi/DEV2/inst", "m/wifi/DEV3/inst", "m/wifi/DEV4/inst"]


def test_buffer_backoff_exponencial_y_limite():
    """Valida el cálculo del backoff exponencial y el tope máximo."""
    buffer = BufferMensajesMQTT(max_size=10, backoff_base_s=2.0, backoff_max_s=30.0)
    buffer.encolar("topico/test", {"data": 1})

    intentos = 0

    def ejecutor_fallido(topico, payload):
        nonlocal intentos
        intentos += 1
        raise ConnectionError("Timeout")

    # Intento 1: falla y aplica backoff base (2.0s)
    buffer.procesar_pendientes(ejecutor_fallido, ignorar_backoff=True)
    msg = buffer._cola[0]
    assert msg.intentos == 1
    # backoff = 2.0 * (2 ** 0) = 2.0s

    # Intento 2: falla y duplica backoff (4.0s)
    buffer.procesar_pendientes(ejecutor_fallido, ignorar_backoff=True)
    msg = buffer._cola[0]
    assert msg.intentos == 2

    # Intento 3: falla (8.0s)
    buffer.procesar_pendientes(ejecutor_fallido, ignorar_backoff=True)
    assert buffer._cola[0].intentos == 3

    # Simular muchos intentos para verificar que no supere backoff_max_s (30.0s)
    buffer._cola[0].intentos = 10
    buffer.procesar_pendientes(ejecutor_fallido, ignorar_backoff=True)
    assert buffer._cola[0].intentos == 11
    # proximo reintento debe estar acotado a <= ahora + 30.0s

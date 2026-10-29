"""tests/unit/test_consumo_mqtt.py — Consumo MQTT por equipo y hora (#93).

El agregado de una hora tiene que coincidir con la suma de los mensajes que el listener loguea en esa hora.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.application.use_cases.consultar_consumo_mqtt import ConsultarConsumoMqttUseCase
from src.domain.telemetria.servicios.consumo_mqtt import (
    AcumuladorConsumoHorario,
    ContadorConsumo,
    hora_inicio,
    normalizar_uid,
    uid_desde_topico,
)
from src.infrastructure.paho_mqtt import mqtt_listener
from src.infrastructure.paho_mqtt.mqtt_listener import MQTTListener
from src.infrastructure.sqlalchemy.models_consumo_mqtt import ConsumoMqttHorarioModel
from src.infrastructure.sqlalchemy.repositories.consumo_mqtt_repository import (
    RepositorioConsumoMqttSqlAlchemy,
    consultar_consumo,
    sumar_consumo,
)

HORA = datetime(2026, 10, 29, 10, 0, tzinfo=timezone.utc)


def test_uid_desde_topico_normaliza_y_rechaza_tópicos_ajenos():
    assert uid_desde_topico("m/wifi/ECC9FFB45488/inst") == "ECC9FFB45488"
    assert uid_desde_topico("m/wifi/ec:c9:ff:b5:7f:20/acc") == "ECC9FFB57F20"
    assert uid_desde_topico("auto24v4m/ABC/inst") is None
    assert uid_desde_topico("m/wifi/") is None
    assert normalizar_uid("d4-8c-49-f0-37-24") == "D48C49F03724"


def test_hora_inicio_trunca_a_la_hora_utc():
    assert hora_inicio(datetime(2026, 10, 29, 10, 54, 12, 5, tzinfo=timezone.utc)) == HORA


def test_acumulador_suma_por_equipo_y_hora_y_extraer_vacia():
    acum = AcumuladorConsumoHorario()
    acum.registrar("ECC9FFB45488", 100, datetime(2026, 10, 29, 10, 1, tzinfo=timezone.utc))
    acum.registrar("ECC9FFB45488", 50, datetime(2026, 10, 29, 10, 59, tzinfo=timezone.utc))
    acum.registrar("ECC9FFB45488", 70, datetime(2026, 10, 29, 11, 0, tzinfo=timezone.utc))
    acum.registrar("D48C49F03724", 10, datetime(2026, 10, 29, 10, 5, tzinfo=timezone.utc))

    datos = acum.extraer()

    assert datos[("ECC9FFB45488", HORA)] == ContadorConsumo(mensajes=2, bytes_payload=150)
    assert datos[("D48C49F03724", HORA)] == ContadorConsumo(mensajes=1, bytes_payload=10)
    assert len(datos) == 3
    assert acum.extraer() == {}


def test_fusionar_devuelve_lo_no_persistido_sin_perder_mensajes():
    acum = AcumuladorConsumoHorario()
    acum.registrar("ECC9FFB45488", 100, HORA)
    pendiente = acum.extraer()
    acum.registrar("ECC9FFB45488", 30, HORA)

    acum.fusionar(pendiente)

    assert acum.extraer()[("ECC9FFB45488", HORA)] == ContadorConsumo(mensajes=2, bytes_payload=130)


def _listener_con_contador_real(monkeypatch) -> tuple[MQTTListener, list[int]]:
    """Listener sin __init__ con el acumulador real, y un logger que captura tamano_bytes de mqtt_mensaje_recibido."""
    listener = MQTTListener.__new__(MQTTListener)
    listener.settings = MagicMock(MQTT_MAX_PAYLOAD_BYTES=65536)
    listener._dedup = MagicMock()
    listener._dedup.es_duplicado.return_value = False
    listener._executor = MagicMock()
    listener._consumo = AcumuladorConsumoHorario()
    logueados: list[int] = []
    logger = MagicMock()
    logger.info.side_effect = lambda evento, **kw: (
        logueados.append(kw["tamano_bytes"]) if evento == "mqtt_mensaje_recibido" else None
    )
    monkeypatch.setattr(mqtt_listener, "logger", logger)
    return listener, logueados


def test_agregado_de_una_hora_coincide_con_la_suma_de_mensajes_del_log(monkeypatch):
    listener, logueados = _listener_con_contador_real(monkeypatch)
    reloj = MagicMock()
    reloj.now.return_value = datetime(2026, 10, 29, 10, 30, tzinfo=timezone.utc)
    payloads = [b'{"t": 1, "f": []}', b'{"t": 2, "f": [{"n": "R", "v": 228.7}]}', b"{}", b'{"t": 3}']

    with patch.object(mqtt_listener, "datetime", reloj):
        for payload in payloads:
            listener._on_message(None, None, MagicMock(topic="m/wifi/ECC9FFB45488/inst", payload=payload))
        # Un tópico ajeno al equipo se loguea pero no suma a ningún equipo.
        listener._on_message(None, None, MagicMock(topic="auto24v4m/X/inst", payload=b'{"a": 1}'))

    datos = listener._consumo.extraer()
    contador = datos[("ECC9FFB45488", HORA)]
    assert contador.mensajes == len(payloads) == 4
    assert contador.bytes_payload == sum(len(p) for p in payloads)
    assert contador.bytes_payload == sum(logueados[:4])
    assert len(logueados) == 5


def test_mensaje_descartado_por_tamano_no_suma(monkeypatch):
    listener, logueados = _listener_con_contador_real(monkeypatch)
    listener.settings = MagicMock(MQTT_MAX_PAYLOAD_BYTES=5)

    listener._on_message(None, None, MagicMock(topic="m/wifi/ECC9FFB45488/inst", payload=b'{"demasiado": 1}'))

    assert listener._consumo.extraer() == {}
    assert logueados == []


@pytest.fixture
def sesion_sqlite():
    engine = create_engine("sqlite://")
    ConsumoMqttHorarioModel.__table__.create(engine)
    return sessionmaker(bind=engine)


def test_sumar_consumo_acumula_sobre_la_misma_fila(sesion_sqlite):
    sumar_consumo(sesion_sqlite, {("ECC9FFB45488", HORA): ContadorConsumo(2, 150)})
    sumar_consumo(sesion_sqlite, {("ECC9FFB45488", HORA): ContadorConsumo(1, 20)})

    filas = consultar_consumo(sesion_sqlite, "ECC9FFB45488", HORA, datetime(2026, 10, 29, 11, tzinfo=timezone.utc))

    assert [(f.mensajes, f.bytes_payload) for f in filas] == [(3, 170)]


def test_consulta_respeta_rango_y_normaliza_uid(sesion_sqlite):
    sumar_consumo(sesion_sqlite, {("ECC9FFB45488", HORA): ContadorConsumo(1, 10)})
    repo = RepositorioConsumoMqttSqlAlchemy(sesion_sqlite)

    caso = ConsultarConsumoMqttUseCase(repo)
    resp = caso.ejecutar("ec:c9:ff:b4:54:88", HORA, datetime(2026, 10, 29, 11, tzinfo=timezone.utc))
    fuera = caso.ejecutar(
        "ECC9FFB45488", datetime(2026, 10, 29, 11, tzinfo=timezone.utc), datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
    )

    assert resp.device_uid == "ECC9FFB45488"
    assert (resp.total_mensajes, resp.total_bytes_payload) == (1, 10)
    assert "No es el consumo del chip" in resp.nota
    assert fuera.horas == []


def test_desde_posterior_a_hasta_se_rechaza():
    repo = MagicMock()
    with pytest.raises(ValueError):
        ConsultarConsumoMqttUseCase(repo).ejecutar("ECC9FFB45488", HORA, HORA)

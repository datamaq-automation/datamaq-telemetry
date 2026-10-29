"""tests/unit/test_develop_replica_solo_lectura.py — Réplica de solo lectura en develop/api-dev (decisión 2026-10-29).

Cubre el corte de persistencia, la compuerta de comandos al broker, el guard de método y el rol de solo lectura.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.use_cases.autenticar_usuario import ROLES_VALIDOS
from src.infrastructure.fastapi.dependencies import requiere_rol_escritura
from src.infrastructure.fastapi.solo_lectura_middleware import (
    SoloLecturaMiddleware,
    excepciones_desde_config,
)
from src.infrastructure.paho_mqtt import mqtt_listener
from src.infrastructure.paho_mqtt.ingesta_sin_escritura import RepositorioSinEscritura, sin_escritura_si
from src.infrastructure.paho_mqtt.mqtt_listener import MQTTListener


class _Repo:
    def __init__(self) -> None:
        self.llamadas: list[str] = []

    def guardar_instantanea(self, lectura):
        self.llamadas.append("guardar_instantanea")
        return lectura

    def guardar(self, dispositivo):
        self.llamadas.append("guardar")
        return dispositivo

    def obtener_por_uid(self, uid):
        self.llamadas.append("obtener_por_uid")
        return "dispositivo"


def test_repositorio_sin_escritura_no_llama_al_repo_en_escrituras_y_devuelve_el_argumento():
    real = _Repo()
    repo = RepositorioSinEscritura(real)

    assert repo.guardar_instantanea("lectura") == "lectura"
    assert repo.guardar({"id": 1}) == {"id": 1}
    assert real.llamadas == []


def test_repositorio_sin_escritura_deja_pasar_las_lecturas():
    real = _Repo()
    repo = RepositorioSinEscritura(real)

    assert repo.obtener_por_uid("AA") == "dispositivo"
    assert real.llamadas == ["obtener_por_uid"]


def test_sin_escritura_si_apagado_devuelve_el_repo_original():
    real = _Repo()
    assert sin_escritura_si(False, real) is real
    assert isinstance(sin_escritura_si(True, real), RepositorioSinEscritura)


def _listener_con_settings(monkeypatch, **flags) -> MQTTListener:
    monkeypatch.setattr(mqtt_listener, "logger", MagicMock())
    listener = MQTTListener.__new__(MQTTListener)
    listener.settings = MagicMock(MQTT_COMANDOS_HABILITADOS=flags.get("comandos", True))
    listener._esta_conectado = True
    listener.client = MagicMock()
    return listener


def test_comandos_apagados_no_publican_ni_siquiera_la_renovacion(monkeypatch):
    listener = _listener_con_settings(monkeypatch, comandos=False)

    assert listener.publicar_comando("m/wifi/ECC9FFB45488/conf/com", {"set": "realtime_sync_mode"}) is False
    assert listener.activar_tiempo_real_dispositivo("ECC9FFB45488", segundos=120) is False
    listener.client.publish.assert_not_called()


def test_comandos_habilitados_publican(monkeypatch):
    listener = _listener_con_settings(monkeypatch, comandos=True)

    assert listener.publicar_comando("m/wifi/ECC9FFB45488/conf/com", {"set": "x"}) is True
    listener.client.publish.assert_called_once()


def _app_con_guard(excepciones: tuple[str, ...] = ()) -> FastAPI:
    app = FastAPI()

    @app.get("/lectura")
    def lectura():
        return {"ok": True}

    @app.post("/escritura")
    def escritura():
        return {"ok": True}

    @app.post("/login")
    def login():
        return {"ok": True}

    app.add_middleware(SoloLecturaMiddleware, excepciones=excepciones)
    return app


def test_guard_bloquea_post_y_deja_pasar_get():
    cliente = TestClient(_app_con_guard())

    assert cliente.get("/lectura").status_code == 200
    respuesta = cliente.post("/escritura")
    assert respuesta.status_code == 403
    assert "solo lectura" in respuesta.json()["detail"]


def test_guard_respeta_excepciones_explicitas():
    cliente = TestClient(_app_con_guard(excepciones=("/login",)))

    assert cliente.post("/login").status_code == 200
    assert cliente.post("/escritura").status_code == 403


def test_excepciones_desde_config_vacio_y_con_comas():
    assert excepciones_desde_config("") == frozenset()
    assert excepciones_desde_config(" /a , /b ,") == frozenset({"/a", "/b"})


def test_rol_solo_lectura_existe_y_no_pasa_el_guard_de_escritura():
    assert "solo_lectura" in ROLES_VALIDOS
    with pytest.raises(Exception) as excinfo:
        requiere_rol_escritura({"rol": "solo_lectura"})
    assert getattr(excinfo.value, "status_code", None) == 403

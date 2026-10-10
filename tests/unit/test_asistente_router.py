# tests/unit/test_asistente_router.py
from fastapi.testclient import TestClient

from src.application.use_cases.asistente.procesar_pregunta_asistente import (
    ProcesarPreguntaAsistenteUseCase,
)
from src.domain.asistente.entities import RespuestaAsistente
from src.infrastructure.fastapi.dependencies import (
    get_procesar_pregunta_asistente_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.routes.asistente_router import router as asistente_router
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import get_settings


def mock_get_usuario_actual():
    return {
        "sub": "usr-test-123",
        "rol": "operador",
        "org": "org-garin",
    }


class _UseCaseFalso:
    def __init__(self, respuesta: RespuestaAsistente | None = None, excepcion: Exception | None = None):
        self._respuesta = respuesta
        self._excepcion = excepcion
        self.llamado_con: dict | None = None

    def ejecutar(
        self,
        pregunta,
        organizacion_id,
        usuario_id,
        conversacion_id=None,
        usuario_consiente_envio_groq=False,
    ):
        self.llamado_con = {
            "pregunta": pregunta,
            "organizacion_id": organizacion_id,
            "usuario_id": usuario_id,
            "conversacion_id": conversacion_id,
        }
        if self._excepcion is not None:
            raise self._excepcion
        return self._respuesta


def _cliente_con_use_case(use_case: ProcesarPreguntaAsistenteUseCase) -> TestClient:
    app = create_app(get_settings())
    # Apagado en create_app (D1): se monta a mano para seguir probando el router.
    app.include_router(asistente_router)
    app.dependency_overrides[get_usuario_actual] = mock_get_usuario_actual
    app.dependency_overrides[get_procesar_pregunta_asistente_use_case] = lambda: use_case
    return TestClient(app)


def test_preguntar_responde_exito_con_intencion_detectada():
    respuesta_esperada = RespuestaAsistente(
        texto="Tenés 2 alertas activas de bajo factor de potencia.",
        intencion="EXPLICAR_ALERTAS",
    )
    use_case = _UseCaseFalso(respuesta=respuesta_esperada)
    client = _cliente_con_use_case(use_case)

    response = client.post(
        "/api/v1/asistente/preguntar",
        json={"pregunta": "¿Por qué tengo alertas?", "conversacion_id": "conv-1"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["respuesta"] == respuesta_esperada.texto
    assert data["intencion_detectada"] == "EXPLICAR_ALERTAS"
    assert use_case.llamado_con == {
        "pregunta": "¿Por qué tengo alertas?",
        "organizacion_id": "org-garin",
        "usuario_id": "usr-test-123",
        "conversacion_id": "conv-1",
    }


def test_preguntar_sin_conversacion_id_es_opcional():
    respuesta_esperada = RespuestaAsistente(texto="Todos los dispositivos están operativos.", intencion="DESCONOCIDO")
    use_case = _UseCaseFalso(respuesta=respuesta_esperada)
    client = _cliente_con_use_case(use_case)

    response = client.post("/api/v1/asistente/preguntar", json={"pregunta": "¿Cómo estamos?"})

    assert response.status_code == 200
    assert use_case.llamado_con["conversacion_id"] is None


def test_preguntar_valida_longitud_minima_de_pregunta():
    use_case = _UseCaseFalso(respuesta=RespuestaAsistente(texto="", intencion=None))
    client = _cliente_con_use_case(use_case)

    response = client.post("/api/v1/asistente/preguntar", json={"pregunta": "a"})

    assert response.status_code == 422


def test_preguntar_traduce_excepcion_interna_a_500():
    use_case = _UseCaseFalso(excepcion=RuntimeError("el modelo de inferencia no respondió"))
    client = _cliente_con_use_case(use_case)

    response = client.post("/api/v1/asistente/preguntar", json={"pregunta": "¿Qué pasó con el medidor 3?"})

    assert response.status_code == 500
    assert response.json()["detail"] == "Ocurrió un error interno en el servidor"
    assert "el modelo de inferencia no respondió" not in response.text

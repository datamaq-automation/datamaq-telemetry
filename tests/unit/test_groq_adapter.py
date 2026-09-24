# tests/unit/test_groq_adapter.py
import json
from unittest.mock import MagicMock, patch

from src.infrastructure.groq.groq_adapter import GroqRespuestaAdapter


def test_generar_sin_api_key_devuelve_respuesta_simulada():
    adapter = GroqRespuestaAdapter(api_key=None)

    resultado = "".join(adapter.generar("¿Cuál es el estado del medidor 1?", "contexto de prueba"))

    assert "Modo Simulación" in resultado
    # Nunca devuelve el contexto crudo (datos de planta sin pasar por el modelo).
    assert "contexto de prueba" not in resultado


def test_generar_con_mock_key_devuelve_respuesta_simulada():
    adapter = GroqRespuestaAdapter(api_key="mock-key")

    resultado = "".join(adapter.generar("¿Hay alertas activas?", "contexto"))

    assert "Modo Simulación" in resultado


def test_generar_con_api_key_real_llama_a_groq_y_devuelve_contenido():
    adapter = GroqRespuestaAdapter(api_key="gsk-real-key-123", model_name="llama-3.3-70b-versatile")

    respuesta_groq = {"choices": [{"message": {"content": "El medidor 1 opera dentro de parámetros normales."}}]}

    fake_response = MagicMock()
    fake_response.read.return_value = json.dumps(respuesta_groq).encode("utf-8")
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False

    with patch("urllib.request.urlopen", return_value=fake_response) as mock_urlopen:
        resultado = "".join(adapter.generar("¿Cómo está el medidor 1?", "contexto real"))

    assert resultado == "El medidor 1 opera dentro de parámetros normales."
    assert mock_urlopen.called
    request_enviado = mock_urlopen.call_args[0][0]
    assert request_enviado.full_url == "https://api.groq.com/openai/v1/chat/completions"
    assert request_enviado.headers["Authorization"] == "Bearer gsk-real-key-123"


def test_generar_con_error_de_red_devuelve_mensaje_de_error():
    adapter = GroqRespuestaAdapter(api_key="gsk-real-key-123")

    with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        resultado = "".join(adapter.generar("¿Cómo está el medidor 1?", "contexto"))

    assert "Error al conectar con el servicio de inferencia Groq" in resultado
    assert "timed out" in resultado

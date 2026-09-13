from collections.abc import Iterator

from src.domain.asistente.ports import GeneradorRespuestaPort
from src.infrastructure.settings.config import get_settings


class GroqRespuestaAdapter(GeneradorRespuestaPort):
    """Adaptador de inferencia LLM en la nube vía Groq (API Key en Settings).

    Ofrece generación en streaming de la respuesta explicativa de telemetría y alertas.
    """

    def __init__(self, api_key: str | None = None, model_name: str = "llama-3.3-70b-versatile"):
        settings = get_settings()
        self._api_key = api_key or getattr(settings, "GROQ_API_KEY", None)
        self._model_name = model_name

    def generar(self, pregunta: str, contexto: str) -> Iterator[str]:
        # Si no hay API Key configurada o se está en entorno de desarrollo/test,
        # devolver una respuesta sintética estructurada
        if not self._api_key or self._api_key == "mock-key":
            yield (
                "[Asistente DataMaq (Modo Simulación / Sin Groq Key)]\n\n"
                f'Analizando tu consulta: *"{pregunta}"*\n\n'
                "A partir de la información procesada de tu planta, se identificaron los siguientes puntos relevantes:\n"
                f"{contexto[:500]}...\n"
            )
            return

        # En caso de contar con API Key real de Groq, realizar la llamada HTTP direct o mediante SDK (aislado)
        try:
            import json
            import urllib.request

            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": self._model_name,
                "messages": [
                    {"role": "system", "content": contexto},
                    {"role": "user", "content": pregunta},
                ],
                "temperature": 0.2,
                "stream": False,
            }
            req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                yield content
        except Exception as err:
            yield f"⚠️ Error al conectar con el servicio de inferencia Groq: {err}"

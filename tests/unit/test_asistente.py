from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.application.dtos.alerta_dto import AlertaResponseDTO
from src.application.dtos.dispositivo_dto import DispositivoResponseDTO
from src.application.use_cases.asistente.procesar_pregunta_asistente import (
    ProcesarPreguntaAsistenteUseCase,
)
from src.infrastructure.asistente.clasificador_reglas import (
    ClasificadorIntencionReglasAdapter,
)
from src.infrastructure.groq.groq_adapter import GroqRespuestaAdapter


def test_clasificador_intencion_reglas():
    clasificador = ClasificadorIntencionReglasAdapter()

    res1 = clasificador.clasificar("¿Por qué recibí una alerta de desconexión en el Trafo Usina?")
    assert res1.nombre == "EXPLICAR_ALERTAS"
    assert res1.confianza >= 0.8

    res2 = clasificador.clasificar("¿Cuál es la salud y estado de los medidores online?")
    assert res2.nombre == "SALUD_DISPOSITIVOS"
    assert res2.confianza >= 0.8

    res3 = clasificador.clasificar("¿Cuál es el consumo de potencia en kW actual?")
    assert res3.nombre == "RESUMEN_TELEMETRIA"
    assert res3.confianza >= 0.8

    res4 = clasificador.clasificar("Hola, ¿cómo estás?")
    assert res4.nombre == "DESCONOCIDO"


def test_procesar_pregunta_asistente_aislamiento_y_sin_alucinaciones():
    # 1. Mocks de dependencias
    clasificador = ClasificadorIntencionReglasAdapter()
    generador = GroqRespuestaAdapter(api_key="mock-key")

    repo_conv = MagicMock()
    conv_mock = MagicMock()
    conv_mock.id = "conv-123"
    repo_conv.crear_conversacion.return_value = conv_mock
    repo_conv.obtener_conversacion.return_value = conv_mock

    gestor_alertas = MagicMock()
    gestor_alertas.listar_alertas.return_value = [
        AlertaResponseDTO(
            id=1,
            dispositivo_id="dev-usina",
            tipo_alerta="CONECTIVIDAD_INESTABLE",
            severidad="WARNING",
            mensaje="⚠️ RSSI: -85 dBm (umbral: -78 dBm)",
            esta_resuelta=False,
            disparada_en=datetime.now(timezone.utc),
            categoria="CONECTIVIDAD",
        )
    ]

    gestor_dispositivos = MagicMock()
    gestor_dispositivos.listar_dispositivos.return_value = [
        DispositivoResponseDTO(
            id="dev-usina",
            device_uid="F8B3B7C0BBB0",
            nombre="Trafo Usina",
            esta_activo=True,
            estado="ONLINE",
            creado_en=datetime.now(timezone.utc),
            actualizado_en=datetime.now(timezone.utc),
        )
    ]

    use_case = ProcesarPreguntaAsistenteUseCase(
        clasificador=clasificador,
        generador=generador,
        repo_conversaciones=repo_conv,
        gestor_alertas=gestor_alertas,
        gestor_dispositivos=gestor_dispositivos,
    )

    # 2. Ejecutar consulta sobre alertas para org-durax
    pregunta = "¿Qué alerta tengo en el Trafo Usina?"
    resultado = use_case.ejecutar(
        pregunta=pregunta,
        organizacion_id="org-durax",
        usuario_id="usr-1",
    )

    # 3. Verificaciones de aislamiento y respuesta sintética
    assert resultado.intencion == "EXPLICAR_ALERTAS"
    assert "CONECTIVIDAD_INESTABLE" in resultado.texto or "Trafo Usina" in resultado.texto

    # Verificar que el gestor de dispositivos fue invocado con la organizacion_id correcta del usuario
    gestor_dispositivos.listar_dispositivos.assert_called_once_with(organizacion_id="org-durax")

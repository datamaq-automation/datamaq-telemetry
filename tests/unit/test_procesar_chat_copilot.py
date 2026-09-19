# tests/unit/test_procesar_chat_copilot.py
from src.application.dtos.copilot_dto import (
    CopilotChatRequestDTO,
    CopilotMensajeHistorialDTO,
)
from src.application.use_cases.copilot.procesar_chat_copilot import (
    ProcesarChatCopilotUseCase,
)


def test_procesar_chat_copilot_bajo_factor_potencia():
    use_case = ProcesarChatCopilotUseCase()
    dto = CopilotChatRequestDTO(
        mensaje="¿Por qué tengo alerta de bajo factor de potencia en el Medidor 1?",
        dispositivo_id="dev-01-garin",
        historial_contexto=[
            CopilotMensajeHistorialDTO(rol="usuario", texto="¿Cuáles son los dispositivos activos?"),
            CopilotMensajeHistorialDTO(rol="asistente", texto="Tenés 3 medidores registrados en Garín."),
        ],
    )

    resultado = use_case.ejecutar(
        dto=dto,
        organizacion_id="org-garin",
        usuario_id="usr-123",
    )

    assert resultado.mensaje_id.startswith("cop-msg-")
    assert "0.88" in resultado.respuesta
    assert resultado.diagnostico_adjunto is not None
    assert resultado.diagnostico_adjunto.requiere_accion is True
    assert resultado.diagnostico_adjunto.sugerencia_kvar == 15.0
    assert resultado.diagnostico_adjunto.alerta_relacionada_id == 1045


def test_procesar_chat_copilot_dispositivo_activo():
    use_case = ProcesarChatCopilotUseCase()
    dto = CopilotChatRequestDTO(
        mensaje="¿El dispositivo está activo?",
        dispositivo_id="dev-01-garin",
    )

    resultado = use_case.ejecutar(
        dto=dto,
        organizacion_id="org-garin",
        usuario_id="usr-123",
    )

    assert "activo" in resultado.respuesta
    assert resultado.diagnostico_adjunto is not None
    assert resultado.diagnostico_adjunto.requiere_accion is False

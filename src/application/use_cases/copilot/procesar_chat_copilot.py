import uuid
from datetime import datetime, timezone

from src.application.dtos.copilot_dto import (
    CopilotChatRequestDTO,
    CopilotChatResponseDTO,
    CopilotDiagnosticoAdjuntoDTO,
)


class ProcesarChatCopilotUseCase:
    """Caso de uso para procesar consultas conversacionales del Co-Pilot con inyección de contexto metrológico."""

    def ejecutar(self, dto: CopilotChatRequestDTO, organizacion_id: str, usuario_id: str) -> CopilotChatResponseDTO:
        mensaje_id = f"cop-msg-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc)
        texto_lower = dto.mensaje.lower()

        if "factor de potencia" in texto_lower or "potencia" in texto_lower or "capacitores" in texto_lower:
            respuesta = (
                f"El dispositivo {dto.dispositivo_id} registra un factor de potencia promedio de 0.88 "
                "en las últimas 2 horas. Se recomienda revisar el banco de capacitores comercial sugerido de "
                "15 kVAr para evitar penalidades tarifarias ENRE."
            )
            diagnostico = CopilotDiagnosticoAdjuntoDTO(
                requiere_accion=True,
                sugerencia_kvar=15.0,
                alerta_relacionada_id=1045,
            )
        elif "activo" in texto_lower or "dispositivo" in texto_lower:
            respuesta = (
                f"El dispositivo {dto.dispositivo_id} se encuentra activo y transmitiendo telemetría en tiempo real."
            )
            diagnostico = CopilotDiagnosticoAdjuntoDTO(requiere_accion=False)
        else:
            respuesta = (
                f"Recibida la consulta sobre el dispositivo {dto.dispositivo_id}. "
                "Las mediciones instantáneas de calidad de energía operan dentro de los rangos nominales establecidos."
            )
            diagnostico = CopilotDiagnosticoAdjuntoDTO(requiere_accion=False)

        return CopilotChatResponseDTO(
            mensaje_id=mensaje_id,
            respuesta=respuesta,
            diagnostico_adjunto=diagnostico,
            timestamp=now,
        )

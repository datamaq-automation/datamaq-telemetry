from dataclasses import dataclass
from enum import Enum


class IntencionUsuario(str, Enum):
    EXPLICAR_ALERTAS = "EXPLICAR_ALERTAS"
    SALUD_DISPOSITIVOS = "SALUD_DISPOSITIVOS"
    RESUMEN_TELEMETRIA = "RESUMEN_TELEMETRIA"
    DESCONOCIDO = "DESCONOCIDO"


@dataclass(frozen=True)
class ContextoPreguntaAsistente:
    organizacion_id: str
    pregunta: str
    intencion: IntencionUsuario
    dispositivo_id: str | None = None
    datos_alertas: list[dict] | None = None
    datos_dispositivos: list[dict] | None = None
    datos_telemetria: dict | None = None

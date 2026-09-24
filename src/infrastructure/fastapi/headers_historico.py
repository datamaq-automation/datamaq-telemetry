"""src/infrastructure/fastapi/headers_historico.py — Header de retención de los históricos de potencia."""

from datetime import datetime, timezone

# Fecha más antigua consultable del histórico (ISO 8601 UTC). Va en header y no en el body para
# que el contrato siga siendo la lista de siempre (cambio aditivo, sin despliegue coordinado).
HEADER_DATOS_DESDE = "X-Datos-Desde"


def formatear_datos_desde(valor: datetime) -> str:
    utc = valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor.astimezone(timezone.utc)
    return utc.isoformat().replace("+00:00", "Z")

"""src/domain/telemetria/servicios/aislamiento_broadcast.py."""
def debe_recibir_evento(
    es_superadmin: bool,
    organizacion_cliente: str | None,
    organizacion_evento: str | None,
) -> bool:
    """Decide si un cliente WebSocket conectado debe recibir un evento de telemetría en vivo.

    Un superadmin ve todo. Un usuario normal solo ve eventos de su propia organización.
    Si el dispositivo emisor no tiene organización resuelta (sin planta asignada), el
    evento se considera sensible por defecto y solo llega a superadmins (fail-closed).
    """
    if es_superadmin:
        return True
    if organizacion_evento is None:
        return False
    return organizacion_cliente == organizacion_evento

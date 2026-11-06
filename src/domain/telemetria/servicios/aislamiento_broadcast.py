"""src/domain/telemetria/servicios/aislamiento_broadcast.py."""


def debe_recibir_evento(
    es_superadmin: bool,
    organizacion_cliente: str | None,
    organizacion_evento: str | None,
    plantas_permitidas: frozenset[str] | set[str] | None = None,
    planta_evento: str | None = None,
) -> bool:
    """Decide si un cliente WebSocket conectado debe recibir un evento de telemetría en vivo.

    Un superadmin ve todo. Un usuario normal solo ve eventos de su propia organización.
    Si el cliente tiene un conjunto de plantas permitidas asignadas explícitamente,
    el evento debe coincidir con alguna de ellas; si no tiene restricción (None),
    recibe eventos de toda la organización.
    Si el dispositivo emisor no tiene organización resuelta (sin planta asignada), el
    evento se considera sensible por defecto y solo llega a superadmins (fail-closed).
    """
    if es_superadmin:
        return True
    if organizacion_evento is None:
        return False
    if organizacion_cliente != organizacion_evento:
        return False
    if plantas_permitidas is not None:
        if planta_evento is None or planta_evento not in plantas_permitidas:
            return False
    return True

"""Tipos anotados compartidos por los DTOs."""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator


def _asegurar_utc(valor: datetime) -> datetime:
    """Normaliza cualquier datetime entrante a UTC *aware*.

    Un datetime *naive* serializa sin offset (`2026-09-01T23:20:00`) y JavaScript
    lo interpreta como hora local, corriendo el valor por el offset del cliente.
    Con el valor *aware*, Pydantic v2 emite `2026-09-01T23:20:00Z` sin necesidad
    de serializadores propios.

    La persistencia ya garantiza aware vía `UtcDateTime`; esto cubre los caminos
    que no pasan por la base: el stream WebSocket, `expira_en` del login y los
    parámetros de consulta que llegan del cliente.
    """
    if valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


FechaHoraUTC = Annotated[datetime, AfterValidator(_asegurar_utc)]

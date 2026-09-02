"""Tipos SQLAlchemy propios del borde de persistencia."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """Garantiza que todo datetime cruce el borde de la base como UTC *aware*.

    MySQL `DATETIME` no almacena offset y nunca lo va a hacer: la convención del
    proyecto es que la columna guarda UTC *wall-clock*. El problema es que el
    driver devuelve datetimes *naive*, y ese naive viaja intacto hasta el DTO,
    donde Pydantic lo serializa sin offset (`2026-09-01T23:20:00`). Un cliente
    JavaScript interpreta ese formato como hora local, así que la API mentía por
    el valor del offset local (3 horas en Argentina).

    Este decorador concentra la conversión en un solo lugar en vez de repetir
    `replace(tzinfo=utc)` en cada mapeo ORM→entidad. Con el valor ya *aware*,
    Pydantic v2 emite `2026-09-01T23:20:00Z` por sí solo, sin serializadores.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        """Al escribir: normaliza a UTC y descarta el tzinfo que la columna no puede guardar.

        Sin esto, un datetime con offset `-03:00` llega al driver, que descarta el
        `tzinfo` y persiste el wall-clock local como si fuera UTC.
        """
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        """Al leer: reinstala el UTC que la columna no pudo conservar."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

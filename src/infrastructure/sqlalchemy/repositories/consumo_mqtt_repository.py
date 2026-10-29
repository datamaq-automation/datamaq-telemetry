"""src/infrastructure/sqlalchemy/repositories/consumo_mqtt_repository.py — Persistencia del consumo MQTT por hora (#93)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.domain.telemetria.servicios.consumo_mqtt import ContadorConsumo
from src.infrastructure.sqlalchemy.models_consumo_mqtt import ConsumoMqttHorarioModel


def sumar_consumo(
    session_factory: sessionmaker[Session],
    datos: dict[tuple[str, datetime], ContadorConsumo],
) -> None:
    """Suma los contadores a las filas (uid, hora) en una sola transacción."""
    with session_factory() as session:
        for (uid, hora), contador in datos.items():
            fila = session.get(ConsumoMqttHorarioModel, (uid, hora))
            if fila is None:
                session.add(
                    ConsumoMqttHorarioModel(
                        uid=uid,
                        hora=hora,
                        mensajes=contador.mensajes,
                        bytes_payload=contador.bytes_payload,
                    )
                )
            else:
                fila.mensajes += contador.mensajes
                fila.bytes_payload += contador.bytes_payload
        session.commit()


def consultar_consumo(
    session_factory: sessionmaker[Session],
    uid: str,
    desde: datetime,
    hasta: datetime,
) -> list[ConsumoMqttHorarioModel]:
    """Filas del equipo con hora en [desde, hasta), ordenadas por hora. Solo lectura."""
    with session_factory() as session:
        consulta = (
            select(ConsumoMqttHorarioModel)
            .where(ConsumoMqttHorarioModel.uid == uid)
            .where(ConsumoMqttHorarioModel.hora >= desde)
            .where(ConsumoMqttHorarioModel.hora < hasta)
            .order_by(ConsumoMqttHorarioModel.hora)
        )
        return list(session.scalars(consulta))


class RepositorioConsumoMqttSqlAlchemy:
    """Adaptador del puerto de lectura sobre ``consultar_consumo``."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def consultar(self, uid: str, desde: datetime, hasta: datetime) -> list[tuple[datetime, int, int]]:
        return [
            (fila.hora, fila.mensajes, fila.bytes_payload)
            for fila in consultar_consumo(self._session_factory, uid, desde, hasta)
        ]

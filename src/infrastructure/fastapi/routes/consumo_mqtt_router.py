"""src/infrastructure/fastapi/routes/consumo_mqtt_router.py — Consulta del consumo MQTT por equipo y hora (#93).

Solo superadmin: es una vista operativa del servidor, no de una planta. Solo lectura.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.application.dtos.consumo_mqtt_dto import ConsumoMqttResponseDTO
from src.application.use_cases.consultar_consumo_mqtt import ConsultarConsumoMqttUseCase
from src.infrastructure.fastapi.dependencies import requiere_rol_superadmin
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.repositories.consumo_mqtt_repository import RepositorioConsumoMqttSqlAlchemy

router = APIRouter(prefix="/api/v1/telemetria", tags=["Telemetría"])


@router.get(
    "/consumo-mqtt",
    response_model=ConsumoMqttResponseDTO,
    dependencies=[Depends(requiere_rol_superadmin)],
    summary="Mensajes y bytes de payload por hora que llegaron al servidor desde un equipo",
)
def obtener_consumo_mqtt(
    device_uid: Annotated[str, Query(min_length=1, max_length=32)],
    desde: Annotated[datetime, Query()],
    hasta: Annotated[datetime, Query()],
) -> ConsumoMqttResponseDTO:
    use_case = ConsultarConsumoMqttUseCase(RepositorioConsumoMqttSqlAlchemy(get_session_factory()))
    try:
        return use_case.ejecutar(device_uid, desde, hasta)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

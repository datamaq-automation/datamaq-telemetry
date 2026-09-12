"""src/infrastructure/fastapi/routes/telemetria_router.py."""
from datetime import datetime, timedelta
from datetime import timezone as tz
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from src.application.dtos.alerta_dto import AlertaResponseDTO
from src.application.dtos.telemetria_dto import (
    AcumuladoEnergiaDTO,
    DiagnosticoFasesDispositivoDTO,
    EnergiaAgregadaDTO,
    LecturaInstantaneaDTO,
    TelemetriaLatestResponseDTO,
)
from src.application.dtos.tipos import FechaHoraUTC
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.application.use_cases.exportar_telemetria import ExportarTelemetriaUseCase
from src.application.use_cases.gestionar_alertas import GestionarAlertasUseCase
from src.infrastructure.fastapi.dependencies import (
    get_alertas_use_case,
    get_exportar_telemetria_use_case,
    get_telemetria_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_dispositivo
from src.infrastructure.fastapi.error_handler import manejar_error_http

router = APIRouter(
    prefix="/api/v1/telemetria",
    tags=["Telemetría"],
    dependencies=[Depends(get_usuario_actual)],
)


@router.get(
    "/latest/{device_id}",
    response_model=TelemetriaLatestResponseDTO,
    dependencies=[Depends(verificar_propiedad_dispositivo)],
)
def get_latest_telemetry(
    device_id: str,
    use_case: Annotated[ConsultarTelemetriaUseCase, Depends(get_telemetria_use_case)],
):
    try:
        return use_case.obtener_ultima_telemetria(device_id)
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/fases-diagnostico/{device_id}",
    response_model=DiagnosticoFasesDispositivoDTO,
    dependencies=[Depends(verificar_propiedad_dispositivo)],
)
def get_phase_diagnostic(
    device_id: str,
    use_case: Annotated[ConsultarTelemetriaUseCase, Depends(get_telemetria_use_case)],
):
    """Diagnóstico metrológico fasorial y evaluación de rotación/desfasaje de canales."""
    try:
        return use_case.diagnosticar_fases(device_id)
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/instantaneous/{device_id}",
    response_model=list[LecturaInstantaneaDTO],
    dependencies=[Depends(verificar_propiedad_dispositivo)],
)
def get_instantaneous_history(
    device_id: str,
    use_case: Annotated[ConsultarTelemetriaUseCase, Depends(get_telemetria_use_case)],
    limit: int = Query(500, ge=1, le=5000, description="Límite máximo de registros a retornar"),
    hours: int | None = Query(None, ge=1, le=720, description="Últimas N horas"),
    granularity: str = Query("auto", description="Granularidad temporal: auto, raw, 1m, 5m, 15m, 1h"),
):
    try:
        desde = datetime.now(tz.utc) - timedelta(hours=hours) if hours else None
        return use_case.listar_instantaneas(
            id_o_uid=device_id,
            limite=limit,
            desde=desde,
            granularidad=granularity,
            horas=hours,
        )
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/energy/{device_id}",
    response_model=list[AcumuladoEnergiaDTO | EnergiaAgregadaDTO],
    dependencies=[Depends(verificar_propiedad_dispositivo)],
)
def get_energy_history(
    device_id: str,
    use_case: Annotated[ConsultarTelemetriaUseCase, Depends(get_telemetria_use_case)],
    limit: int = Query(100, le=1000),
    days: int | None = Query(None, description="Últimos N días"),
    granularity: Literal["raw", "day", "month"] = Query("raw", description="Granularidad: raw, day, month"),
    timezone: str = Query("America/Argentina/Buenos_Aires", description="Zona horaria IANA"),
):
    try:
        if granularity == "raw":
            desde = datetime.now(tz.utc) - timedelta(days=days) if days else None
            return use_case.listar_energias(device_id, limit, desde)
        return use_case.listar_energia_agregada(device_id, granularity, timezone, days)
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/alerts/{device_id}",
    response_model=list[AlertaResponseDTO],
    dependencies=[Depends(verificar_propiedad_dispositivo)],
)
def get_alerts_history(
    device_id: str,
    use_case: Annotated[GestionarAlertasUseCase, Depends(get_alertas_use_case)],
    solo_abiertas: bool = Query(False, description="Filtrar solo alertas no resueltas"),
    severidad: str | None = Query(None, description="Filtrar por severidad (INFO, WARNING, CRITICAL)"),
    limit: int = Query(100, le=500, description="Límite de registros"),
    desde: FechaHoraUTC | None = Query(None, description="Fecha de inicio ISO8601"),
    hasta: FechaHoraUTC | None = Query(None, description="Fecha de fin ISO8601"),
):
    try:
        return use_case.listar_alertas(
            dispositivo_id=device_id,
            solo_abiertas=solo_abiertas,
            severidad=severidad,
            limite=limit,
            desde=desde,
            hasta=hasta,
        )
    except Exception as e:
        manejar_error_http(e)


@router.get("/exportar/csv", dependencies=[Depends(verificar_propiedad_dispositivo)])
def exportar_telemetria_csv(
    dispositivo_id: str = Query(..., description="ID del dispositivo a exportar"),
    use_case: Annotated[ExportarTelemetriaUseCase, Depends(get_exportar_telemetria_use_case)] = None,  # type: ignore
    desde: FechaHoraUTC | None = Query(None, description="Fecha de inicio ISO8601 UTC"),
    hasta: FechaHoraUTC | None = Query(None, description="Fecha de fin ISO8601 UTC"),
    limite: int = Query(10000, ge=1, le=50000, description="Límite máximo de lecturas"),
):
    try:
        stream = use_case.ejecutar(
            dispositivo_id=dispositivo_id,
            desde=desde,
            hasta=hasta,
            limite=limite,
        )
        ts = datetime.now(tz.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"telemetria_{dispositivo_id}_{ts}.csv"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(stream, media_type="text/csv; charset=utf-8", headers=headers)
    except Exception as e:
        manejar_error_http(e)

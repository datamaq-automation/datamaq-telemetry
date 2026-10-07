"""src/infrastructure/fastapi/routes/telemetria_router.py."""

from datetime import datetime, timedelta
from datetime import timezone as tz
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
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
from src.application.use_cases.agregacion_dispositivos import calcular_potencia_referencia
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.application.use_cases.exportar_telemetria import ExportarTelemetriaUseCase
from src.application.use_cases.gestionar_alertas import GestionarAlertasUseCase
from src.domain.telemetria.value_objects import (
    PeriodoTelemetria,
    obtener_default_granularidad,
    validar_granularidad,
)
from src.infrastructure.fastapi.dependencies import (
    get_alertas_use_case,
    get_exportar_telemetria_use_case,
    get_telemetria_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_dispositivo
from src.infrastructure.fastapi.error_handler import manejar_error_http
from src.infrastructure.fastapi.headers_historico import (
    HEADER_DATOS_DESDE,
    formatear_datos_desde,
    setear_potencia_referencia,
)

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
    response: Response,
    use_case: Annotated[ConsultarTelemetriaUseCase, Depends(get_telemetria_use_case)],
    limit: int = Query(500, ge=1, le=5000, description="Límite máximo de registros a retornar"),
    hours: int | None = Query(None, ge=1, le=720, description="Últimas N horas"),
    granularity: str = Query(
        "auto",
        description="Granularidad temporal: auto, raw, 1m, 5m, 15m, 1h, lttb (downsampling con preservación de picos)",
    ),
    hasta: FechaHoraUTC | None = Query(
        None, description="Fin de la ventana ISO8601 UTC; la ventana es [hasta - hours, hasta]. Sin valor: ahora"
    ),
):
    """El header `X-Datos-Desde` informa la fecha más antigua consultable (corte de retención) y
    `X-Potencia-Referencia-W` el P99 de potencia activa de los últimos 30 días (omitido sin datos
    suficientes), independiente de `hours` y `hasta`."""
    try:
        fin_ventana = hasta or datetime.now(tz.utc)
        desde = fin_ventana - timedelta(hours=hours) if hours else None
        historico = use_case.historico_instantaneas(
            id_o_uid=device_id,
            limite=limit,
            desde=desde,
            granularidad=granularity,
            horas=hours,
            hasta=hasta,
        )
        response.headers[HEADER_DATOS_DESDE] = formatear_datos_desde(historico.datos_desde)
        setear_potencia_referencia(
            response, ("dispositivo", device_id), lambda: calcular_potencia_referencia([device_id], use_case)
        )
        return historico.lecturas
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/power/{device_id}",
    response_model=list[dict[str, object]],
    dependencies=[Depends(verificar_propiedad_dispositivo)],
)
def get_power_history(
    device_id: str,
    response: Response,
    use_case: Annotated[ConsultarTelemetriaUseCase, Depends(get_telemetria_use_case)],
    periodo: PeriodoTelemetria = Query("24h", description="Período: 24h, 7d, 30d"),
    granularidad: str | None = Query(
        None,
        description="Granularidad temporal: 5m, 15m, 30m, 1h, 1d. Si omitido, se aplica default según período.",
    ),
    limit: int = Query(1000, le=5000, description="Límite máximo de registros"),
):
    """Histórico de potencia con granularidad configurable.

    Parámetros:
    - `periodo`: 24h, 7d, 30d
    - `granularidad`: opcional. Si omitido, se usa default según período.
      * 24h: [5m, 15m, 30m] → default 5m
      * 7d: [15m, 30m, 1h] → default 30m
      * 30d: [1h, 1d] → default 1h
    """
    try:
        # Validar granularidad
        if granularidad:
            gran_validada = validar_granularidad(granularidad, periodo)
        else:
            gran_validada = obtener_default_granularidad(periodo)

        # Calcular ventana temporal
        ahora = datetime.now(tz.utc)
        duracion = {"24h": 1, "7d": 7, "30d": 30}[periodo]
        desde = ahora - timedelta(days=duracion)

        # Para MVP: retornar datos instantáneos de potencia
        # En versión futura: agregar según granularidad
        lecturas = use_case.historico_instantaneas(
            id_o_uid=device_id,
            limite=limit,
            desde=desde,
        )

        response.headers[HEADER_DATOS_DESDE] = formatear_datos_desde(use_case.datos_desde(device_id))
        # Agregar header con granularidad aplicada
        response.headers["X-Granularidad"] = gran_validada.value

        return [dict(r) if isinstance(r, dict) else {"raw": r} for r in lecturas]

    except ValueError as e:
        # Validación de granularidad/período
        manejar_error_http(e)
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/energy/{device_id}",
    response_model=list[AcumuladoEnergiaDTO | EnergiaAgregadaDTO],
    dependencies=[Depends(verificar_propiedad_dispositivo)],
)
def get_energy_history(
    device_id: str,
    response: Response,
    use_case: Annotated[ConsultarTelemetriaUseCase, Depends(get_telemetria_use_case)],
    limit: int = Query(100, le=1000),
    days: int | None = Query(None, description="Últimos N días"),
    granularity: Literal["raw", "day", "month"] = Query("raw", description="Granularidad: raw, day, month"),
    granularidad: str | None = Query(
        None,
        description="Granularidad temporal (nuevo): 5m, 15m, 30m, 1h, 1d. Incompatible con `granularity`.",
    ),
    timezone: str = Query("America/Argentina/Buenos_Aires", description="Zona horaria IANA"),
):
    """El header `X-Datos-Desde` informa el corte de retención: `days` se acota a él sin aviso en
    el body, así que el frontend lo necesita para titular el período real.

    Soporta dos esquemas de granularidad:
    - Legado: `granularity` (raw|day|month)
    - Nuevo: `granularidad` (5m|15m|30m|1h|1d) con validación por período
    """
    try:
        # Validar si se proporcionó granularidad nueva
        if granularidad:
            # Inducir período a partir de days o usar default 24h
            periodo: PeriodoTelemetria = "24h"
            if days:
                if days <= 1:
                    periodo = "24h"
                elif days <= 7:
                    periodo = "7d"
                else:
                    periodo = "30d"

            # Validar granularidad
            validar_granularidad(granularidad, periodo)

        # Lógica original
        if granularity == "raw":
            desde = datetime.now(tz.utc) - timedelta(days=days) if days else None
            energias = use_case.listar_energias(device_id, limit, desde)
        else:
            energias = use_case.listar_energia_agregada(device_id, granularity, timezone, days)

        response.headers[HEADER_DATOS_DESDE] = formatear_datos_desde(use_case.datos_desde(device_id))
        return energias

    except ValueError as e:
        # Validación de granularidad
        manejar_error_http(e)
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

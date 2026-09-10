from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.application.dtos.disponibilidad_dto import (
    CorregirClasificacionRequestDTO,
    EventoDisponibilidadResponseDTO,
    MetricasDisponibilidadOEEResponseDTO,
    ParadaProgramadaCreateDTO,
    ParadaProgramadaResponseDTO,
)
from src.application.dtos.maquina_dto import (
    HistogramaPotenciaResponseDTO,
    MaquinaCreateDTO,
    MaquinaResponseDTO,
    MaquinaUpdateDTO,
)
from src.application.use_cases.exportar_disponibilidad import (
    ExportarDisponibilidadUseCase,
)
from src.application.use_cases.gestionar_disponibilidad import GestionarDisponibilidadUseCase
from src.application.use_cases.gestionar_maquinas import GestionarMaquinasUseCase
from src.infrastructure.fastapi.dependencies import (
    get_disponibilidad_use_case,
    get_exportar_disponibilidad_use_case,
    get_maquinas_use_case,
    get_usuario_actual,
    requiere_rol_escritura,
)
from src.infrastructure.fastapi.device_ownership import (
    verificar_propiedad_evento_disponibilidad,
    verificar_propiedad_maquina,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http

router = APIRouter(
    prefix="/api/v1/disponibilidad",
    tags=["Disponibilidad de Máquina"],
    dependencies=[Depends(get_usuario_actual)],
)


def _organizacion_de_claims(claims: dict[str, Any]) -> str | None:
    if claims.get("rol") in ("superadmin", "invitado_global"):
        return None
    return claims.get("org")


@router.get("/maquinas", response_model=list[MaquinaResponseDTO])
def listar_maquinas(
    use_case: Annotated[GestionarMaquinasUseCase, Depends(get_maquinas_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
):
    if claims.get("rol") not in ("superadmin", "invitado_global") and not claims.get("org"):
        return []
    try:
        return use_case.listar_maquinas(_organizacion_de_claims(claims))
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/maquinas/{maquina_id}",
    response_model=MaquinaResponseDTO,
    dependencies=[Depends(verificar_propiedad_maquina)],
)
def obtener_maquina(
    maquina_id: str,
    use_case: Annotated[GestionarMaquinasUseCase, Depends(get_maquinas_use_case)],
):
    try:
        return use_case.obtener_maquina(maquina_id)
    except Exception as e:
        manejar_error_http(e)


@router.post("/maquinas", response_model=MaquinaResponseDTO, dependencies=[Depends(requiere_rol_escritura)])
def registrar_maquina(
    dto: MaquinaCreateDTO,
    use_case: Annotated[GestionarMaquinasUseCase, Depends(get_maquinas_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
):
    organizacion_id = _organizacion_de_claims(claims)
    if claims.get("rol") not in ("superadmin", "invitado_global") and not organizacion_id:
        raise HTTPException(status_code=403, detail="sin_organizacion_asignada")
    try:
        return use_case.registrar_maquina(dto, organizacion_id)
    except Exception as e:
        manejar_error_http(e)


@router.patch(
    "/maquinas/{maquina_id}",
    response_model=MaquinaResponseDTO,
    dependencies=[Depends(requiere_rol_escritura), Depends(verificar_propiedad_maquina)],
)
def actualizar_maquina(
    maquina_id: str,
    dto: MaquinaUpdateDTO,
    use_case: Annotated[GestionarMaquinasUseCase, Depends(get_maquinas_use_case)],
):
    try:
        return use_case.actualizar_maquina(maquina_id, dto)
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/maquinas/{maquina_id}/histograma",
    response_model=HistogramaPotenciaResponseDTO,
    dependencies=[Depends(verificar_propiedad_maquina)],
)
def obtener_histograma(
    maquina_id: str,
    use_case: Annotated[GestionarMaquinasUseCase, Depends(get_maquinas_use_case)],
    dias: Annotated[int, Query(ge=1, le=90)] = 7,
):
    try:
        return use_case.calcular_histograma(maquina_id, dias=dias)
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/maquinas/{maquina_id}/eventos",
    response_model=list[EventoDisponibilidadResponseDTO],
    dependencies=[Depends(verificar_propiedad_maquina)],
)
def listar_eventos(
    maquina_id: str,
    use_case: Annotated[GestionarDisponibilidadUseCase, Depends(get_disponibilidad_use_case)],
    limite: Annotated[int, Query(ge=1, le=1000)] = 100,
):
    try:
        return use_case.listar_eventos(maquina_id, limite=limite)
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/maquinas/{maquina_id}/metricas-oee",
    response_model=MetricasDisponibilidadOEEResponseDTO,
    dependencies=[Depends(verificar_propiedad_maquina)],
)
def obtener_metricas_oee(
    maquina_id: str,
    use_case: Annotated[GestionarDisponibilidadUseCase, Depends(get_disponibilidad_use_case)],
    desde: Annotated[datetime | None, Query(description="Fecha inicio ISO8601")] = None,
    hasta: Annotated[datetime | None, Query(description="Fecha fin ISO8601")] = None,
    dias: Annotated[int, Query(ge=1, le=90, description="Días hacia atrás si no se especifica desde")] = 7,
):
    try:
        return use_case.calcular_metricas_oee(maquina_id, desde=desde, hasta=hasta, dias=dias)
    except Exception as e:
        manejar_error_http(e)


@router.post(
    "/eventos/{evento_id}/corregir",
    response_model=EventoDisponibilidadResponseDTO,
    dependencies=[Depends(requiere_rol_escritura), Depends(verificar_propiedad_evento_disponibilidad)],
)
@router.patch(
    "/eventos/{evento_id}/corregir",
    response_model=EventoDisponibilidadResponseDTO,
    dependencies=[Depends(requiere_rol_escritura), Depends(verificar_propiedad_evento_disponibilidad)],
)
def corregir_clasificacion(
    evento_id: int,
    dto: CorregirClasificacionRequestDTO,
    use_case: Annotated[GestionarDisponibilidadUseCase, Depends(get_disponibilidad_use_case)],
    claims: Annotated[dict, Depends(requiere_rol_escritura)],
):
    try:
        usuario_id = claims.get("sub", "desconocido")
        return use_case.corregir_clasificacion(evento_id, dto, usuario_id=usuario_id)
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/paradas-programadas",
    response_model=list[ParadaProgramadaResponseDTO],
    dependencies=[Depends(verificar_propiedad_maquina)],
)
def listar_paradas_programadas(
    use_case: Annotated[GestionarDisponibilidadUseCase, Depends(get_disponibilidad_use_case)],
    maquina_id: Annotated[str, Query()],
):
    try:
        return use_case.listar_paradas_programadas(maquina_id)
    except Exception as e:
        manejar_error_http(e)


@router.post(
    "/paradas-programadas",
    response_model=ParadaProgramadaResponseDTO,
    dependencies=[Depends(requiere_rol_escritura)],
)
def registrar_parada_programada(
    dto: ParadaProgramadaCreateDTO,
    use_case: Annotated[GestionarDisponibilidadUseCase, Depends(get_disponibilidad_use_case)],
    claims: Annotated[dict, Depends(requiere_rol_escritura)],
):
    organizacion_id = _organizacion_de_claims(claims)
    if claims.get("rol") not in ("superadmin", "invitado_global") and not organizacion_id:
        raise HTTPException(status_code=403, detail="sin_organizacion_asignada")
    try:
        usuario_id = claims.get("sub")
        return use_case.registrar_parada_programada(dto, usuario_id=usuario_id, organizacion_id=organizacion_id)
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/maquinas/{maquina_id}/exportar/csv",
    dependencies=[Depends(verificar_propiedad_maquina)],
)
def exportar_disponibilidad_csv(
    maquina_id: str,
    use_case: Annotated[ExportarDisponibilidadUseCase, Depends(get_exportar_disponibilidad_use_case)],
    desde: Annotated[datetime | None, Query(description="Fecha inicio ISO8601")] = None,
    hasta: Annotated[datetime | None, Query(description="Fecha fin ISO8601")] = None,
    dias: Annotated[int, Query(ge=1, le=90, description="Días hacia atrás si no se especifica desde")] = 30,
):
    try:
        stream = use_case.ejecutar(maquina_id=maquina_id, desde=desde, hasta=hasta, dias=dias)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"disponibilidad_{maquina_id}_{ts}.csv"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(stream, media_type="text/csv; charset=utf-8", headers=headers)
    except Exception as e:
        manejar_error_http(e)

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.application.dtos.disponibilidad_dto import (
    CorregirClasificacionRequestDTO,
    EventoDisponibilidadResponseDTO,
    ParadaProgramadaCreateDTO,
    ParadaProgramadaResponseDTO,
)
from src.application.dtos.maquina_dto import (
    HistogramaPotenciaResponseDTO,
    MaquinaCreateDTO,
    MaquinaResponseDTO,
    MaquinaUpdateDTO,
)
from src.application.use_cases.gestionar_disponibilidad import GestionarDisponibilidadUseCase
from src.application.use_cases.gestionar_maquinas import GestionarMaquinasUseCase
from src.infrastructure.fastapi.dependencies import (
    get_disponibilidad_use_case,
    get_maquinas_use_case,
    get_usuario_actual,
    requiere_rol_escritura,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http

router = APIRouter(
    prefix="/api/v1/disponibilidad",
    tags=["Disponibilidad de Máquina"],
    dependencies=[Depends(get_usuario_actual)],
)


@router.get("/maquinas", response_model=list[MaquinaResponseDTO])
def listar_maquinas(
    use_case: Annotated[GestionarMaquinasUseCase, Depends(get_maquinas_use_case)],
):
    try:
        return use_case.listar_maquinas()
    except Exception as e:
        manejar_error_http(e)


@router.get("/maquinas/{maquina_id}", response_model=MaquinaResponseDTO)
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
):
    try:
        return use_case.registrar_maquina(dto)
    except Exception as e:
        manejar_error_http(e)


@router.patch(
    "/maquinas/{maquina_id}", response_model=MaquinaResponseDTO, dependencies=[Depends(requiere_rol_escritura)]
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


@router.get("/maquinas/{maquina_id}/histograma", response_model=HistogramaPotenciaResponseDTO)
def obtener_histograma(
    maquina_id: str,
    use_case: Annotated[GestionarMaquinasUseCase, Depends(get_maquinas_use_case)],
    dias: Annotated[int, Query(ge=1, le=90)] = 7,
):
    try:
        return use_case.calcular_histograma(maquina_id, dias=dias)
    except Exception as e:
        manejar_error_http(e)


@router.get("/maquinas/{maquina_id}/eventos", response_model=list[EventoDisponibilidadResponseDTO])
def listar_eventos(
    maquina_id: str,
    use_case: Annotated[GestionarDisponibilidadUseCase, Depends(get_disponibilidad_use_case)],
    limite: Annotated[int, Query(ge=1, le=1000)] = 100,
):
    try:
        return use_case.listar_eventos(maquina_id, limite=limite)
    except Exception as e:
        manejar_error_http(e)


@router.post(
    "/eventos/{evento_id}/corregir",
    response_model=EventoDisponibilidadResponseDTO,
    dependencies=[Depends(requiere_rol_escritura)],
)
@router.patch(
    "/eventos/{evento_id}/corregir",
    response_model=EventoDisponibilidadResponseDTO,
    dependencies=[Depends(requiere_rol_escritura)],
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


@router.get("/paradas-programadas", response_model=list[ParadaProgramadaResponseDTO])
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
    try:
        usuario_id = claims.get("sub")
        return use_case.registrar_parada_programada(dto, usuario_id=usuario_id)
    except Exception as e:
        manejar_error_http(e)

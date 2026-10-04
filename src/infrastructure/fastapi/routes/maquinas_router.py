"""src/infrastructure/fastapi/routes/maquinas_router.py."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from src.application.dtos.maquina_dto import (
    AnalisisConsumoResponseDTO,
    AtribucionConsumoResponseDTO,
    CampanaCreateDTO,
    CampanaResponseDTO,
    CargaCreateDTO,
    CargaResponseDTO,
    CargaUpdateDTO,
    CorregirIntervaloRequestDTO,
    FirmaManualRequestDTO,
    IntervaloActividadResponseDTO,
    PerfilConsumoResponseDTO,
)
from src.application.mappers.maquina_mapper import MáquinaMapper
from src.application.use_cases.analizar_consumo import ZONA_POR_DEFECTO, AnalizarConsumoUseCase
from src.application.use_cases.atribuir_consumo import AtribuirConsumoUseCase
from src.application.use_cases.caracterizar_carga import CaracterizarCargaUseCase
from src.application.use_cases.exportar_cargas import ExportarCargasUseCase
from src.application.use_cases.gestionar_cargas import GestionarCargasUseCase
from src.domain.maquinas.servicios.presets_cargas import CatalogoPresetsCargas
from src.infrastructure.fastapi.dependencies import (
    get_analisis_consumo_use_case,
    get_atribucion_use_case,
    get_caracterizacion_use_case,
    get_cargas_use_case,
    get_exportar_cargas_use_case,
    get_usuario_actual,
    requiere_rol_escritura,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http

router = APIRouter(
    prefix="/api/v1/cargas",
    tags=["Desagregación de Cargas"],
    dependencies=[Depends(get_usuario_actual)],
)


@router.get("", response_model=list[CargaResponseDTO])
def listar_cargas(
    use_case: Annotated[GestionarCargasUseCase, Depends(get_cargas_use_case)],
    device_id: Annotated[str | None, Query(description="Filtrar por dispositivo (UUID o MAC).")] = None,
    solo_activas: bool = False,
):
    try:
        return use_case.listar_cargas(dispositivo_id=device_id, solo_activas=solo_activas)
    except Exception as e:
        manejar_error_http(e)


@router.get("/perfil", response_model=PerfilConsumoResponseDTO)
def perfilar_consumo(
    use_case: Annotated[AnalizarConsumoUseCase, Depends(get_analisis_consumo_use_case)],
    device_id: Annotated[str, Query(description="Dispositivo a analizar (UUID).")],
    dias: Annotated[int, Query(ge=1, le=365)] = 14,
    zona: str = ZONA_POR_DEFECTO,
):
    """Línea de base, ciclado y regímenes de un medidor agregado, sin firmas calibradas.

    Declarado antes que `/{carga_id}` a propósito: si no, FastAPI leería "perfil" como
    el id de una carga.
    """
    try:
        return use_case.perfilar(device_id, dias=dias, zona=zona)
    except Exception as e:
        manejar_error_http(e)


@router.get("/atribucion", response_model=AtribucionConsumoResponseDTO)
def obtener_atribucion(
    use_case: Annotated[AtribuirConsumoUseCase, Depends(get_atribucion_use_case)],
    device_id: Annotated[str, Query(description="Dispositivo a analizar (UUID).")],
    dias: Annotated[int, Query(ge=1, le=365)] = 30,
):
    """Reparto de kWh del período entre las cargas, con el residual explícito.

    El total sale del contador acumulado, que es exacto; el residual es lo que el motor
    no puede explicar y a esta cadencia siempre habrá algo ahí.
    """
    try:
        return use_case.atribucion(device_id, dias=dias)
    except Exception as e:
        manejar_error_http(e)


@router.post("/analisis", response_model=AnalisisConsumoResponseDTO, dependencies=[Depends(requiere_rol_escritura)])
def disparar_analisis(
    use_case: Annotated[AtribuirConsumoUseCase, Depends(get_atribucion_use_case)],
    device_id: Annotated[str, Query(description="Dispositivo a analizar (UUID).")],
    dias: Annotated[int, Query(ge=1, le=365)] = 7,
):
    """Corre el batch de detección y atribución sobre la ventana. Idempotente."""
    try:
        return use_case.analizar(device_id, dias=dias)
    except Exception as e:
        manejar_error_http(e)


@router.patch(
    "/intervalos/{intervalo_id}/corregir",
    response_model=IntervaloActividadResponseDTO,
    dependencies=[Depends(requiere_rol_escritura)],
)
def corregir_intervalo(
    intervalo_id: int,
    dto: CorregirIntervaloRequestDTO,
    use_case: Annotated[AtribuirConsumoUseCase, Depends(get_atribucion_use_case)],
    usuario: Annotated[dict, Depends(get_usuario_actual)],
):
    """Reimputa un intervalo a mano.

    La corrección queda protegida: el batch no la revierte al reprocesar. Estas filas
    son el dataset etiquetado del que después puede salir un modelo.
    """
    try:
        return use_case.corregir_intervalo(intervalo_id, dto, usuario_id=usuario.get("sub", ""))
    except Exception as e:
        manejar_error_http(e)


@router.get("/presets", response_model=list[CargaResponseDTO])
def obtener_presets_catalogo():
    """Catálogo de presets estándar con firmas de fábrica de referencia."""
    try:
        presets = CatalogoPresetsCargas.obtener_todas("preset-catalogo")
        return [MáquinaMapper.to_dto(p) for p in presets]
    except Exception as e:
        manejar_error_http(e)


@router.post(
    "/presets/inicializar",
    response_model=list[CargaResponseDTO],
    dependencies=[Depends(requiere_rol_escritura)],
)
def inicializar_presets_catalogo(
    use_case: Annotated[AtribuirConsumoUseCase, Depends(get_atribucion_use_case)],
    device_id: Annotated[str, Query(description="Dispositivo al que inicializar catálogo.")],
):
    """Crea en el catálogo del medidor las 9 cargas precalibradas estándar que no existan."""
    try:
        cargas = use_case.inicializar_presets_catalogo(device_id)
        return [MáquinaMapper.to_dto(c) for c in cargas]
    except Exception as e:
        manejar_error_http(e)


@router.get("/intervalos", response_model=list[IntervaloActividadResponseDTO])
def listar_intervalos(
    use_case: Annotated[AtribuirConsumoUseCase, Depends(get_atribucion_use_case)],
    device_id: Annotated[str, Query(description="Dispositivo a consultar (UUID).")],
    desde: datetime | None = None,
    hasta: datetime | None = None,
    dias: Annotated[int, Query(ge=1, le=365)] = 7,
    solo_no_atribuidos: bool = False,
    limite: Annotated[int, Query(ge=1, le=1000)] = 200,
):
    """Lista intervalos de actividad del dispositivo, permitiendo filtrar solo los no atribuidos."""
    try:
        return use_case.listar_intervalos_dispositivo(
            dispositivo_id=device_id,
            desde=desde,
            hasta=hasta,
            dias=dias,
            solo_no_atribuidos=solo_no_atribuidos,
            limite=limite,
        )
    except Exception as e:
        manejar_error_http(e)


@router.get("/{carga_id}", response_model=CargaResponseDTO)
def obtener_carga(
    carga_id: str,
    use_case: Annotated[GestionarCargasUseCase, Depends(get_cargas_use_case)],
):
    try:
        return use_case.obtener_carga(carga_id)
    except Exception as e:
        manejar_error_http(e)


@router.post("", response_model=CargaResponseDTO, dependencies=[Depends(requiere_rol_escritura)])
def registrar_carga(
    dto: CargaCreateDTO,
    use_case: Annotated[GestionarCargasUseCase, Depends(get_cargas_use_case)],
):
    try:
        return use_case.registrar_carga(dto)
    except Exception as e:
        manejar_error_http(e)


@router.patch("/{carga_id}", response_model=CargaResponseDTO, dependencies=[Depends(requiere_rol_escritura)])
def actualizar_carga(
    carga_id: str,
    dto: CargaUpdateDTO,
    use_case: Annotated[GestionarCargasUseCase, Depends(get_cargas_use_case)],
):
    try:
        return use_case.actualizar_carga(carga_id, dto)
    except Exception as e:
        manejar_error_http(e)


@router.put("/{carga_id}/firma", response_model=CargaResponseDTO, dependencies=[Depends(requiere_rol_escritura)])
def fijar_firma_manual(
    carga_id: str,
    dto: FirmaManualRequestDTO,
    use_case: Annotated[GestionarCargasUseCase, Depends(get_cargas_use_case)],
):
    """Sobreescritura idempotente de la firma de una carga (calibración manual)."""
    try:
        return use_case.fijar_firma_manual(carga_id, dto)
    except Exception as e:
        manejar_error_http(e)


@router.post(
    "/campanas/activas",
    response_model=CampanaResponseDTO,
    dependencies=[Depends(requiere_rol_escritura)],
)
def iniciar_campana_activa(
    dto: CampanaCreateDTO,
    use_case: Annotated[CaracterizarCargaUseCase, Depends(get_caracterizacion_use_case)],
    usuario: Annotated[dict, Depends(get_usuario_actual)],
):
    """Abre una campaña sobre una carga que se puede prender a voluntad.

    Dejá correr ~60 s antes de prender el aparato: esa ventana inicial es la que mide
    la línea de base contra la que se resta todo lo demás.
    """
    try:
        return use_case.iniciar_activa(dto, usuario_id=usuario.get("sub"))
    except Exception as e:
        manejar_error_http(e)


@router.post(
    "/campanas/pasivas",
    response_model=CampanaResponseDTO,
    dependencies=[Depends(requiere_rol_escritura)],
)
def iniciar_campana_pasiva(
    dto: CampanaCreateDTO,
    use_case: Annotated[CaracterizarCargaUseCase, Depends(get_caracterizacion_use_case)],
    usuario: Annotated[dict, Depends(get_usuario_actual)],
):
    """Abre una campaña de observación para cargas que ciclan solas (heladera, freezer,
    termotanque). Requiere apagar el resto y una ventana larga: varias horas."""
    try:
        return use_case.iniciar_pasiva(dto, usuario_id=usuario.get("sub"))
    except Exception as e:
        manejar_error_http(e)


@router.get("/campanas/{campana_id}", response_model=CampanaResponseDTO)
def obtener_campana(
    campana_id: str,
    use_case: Annotated[CaracterizarCargaUseCase, Depends(get_caracterizacion_use_case)],
):
    try:
        return use_case.obtener(campana_id)
    except Exception as e:
        manejar_error_http(e)


@router.patch(
    "/campanas/{campana_id}/finalizar",
    response_model=CampanaResponseDTO,
    dependencies=[Depends(requiere_rol_escritura)],
)
def finalizar_campana(
    campana_id: str,
    use_case: Annotated[CaracterizarCargaUseCase, Depends(get_caracterizacion_use_case)],
):
    """Cierra la campaña y calcula la firma. Si salió contaminada no fija ninguna firma
    y devuelve el motivo: corresponde repetir la medición."""
    try:
        return use_case.finalizar(campana_id)
    except Exception as e:
        manejar_error_http(e)


@router.patch(
    "/campanas/{campana_id}/descartar",
    response_model=CampanaResponseDTO,
    dependencies=[Depends(requiere_rol_escritura)],
)
def descartar_campana(
    campana_id: str,
    use_case: Annotated[CaracterizarCargaUseCase, Depends(get_caracterizacion_use_case)],
    motivo: str | None = None,
):
    try:
        return use_case.descartar(campana_id, motivo=motivo)
    except Exception as e:
        manejar_error_http(e)


@router.get("/{carga_id}/campanas", response_model=list[CampanaResponseDTO])
def listar_campanas_de_carga(
    carga_id: str,
    use_case: Annotated[CaracterizarCargaUseCase, Depends(get_caracterizacion_use_case)],
):
    try:
        return use_case.listar_por_carga(carga_id)
    except Exception as e:
        manejar_error_http(e)


@router.get("/{carga_id}/intervalos", response_model=list[IntervaloActividadResponseDTO])
def listar_intervalos_de_carga(
    carga_id: str,
    use_case: Annotated[AtribuirConsumoUseCase, Depends(get_atribucion_use_case)],
    limite: Annotated[int, Query(ge=1, le=1000)] = 100,
):
    try:
        return use_case.listar_intervalos(carga_id, limite=limite)
    except Exception as e:
        manejar_error_http(e)


@router.get("/exportar/csv")
def exportar_cargas_csv(
    dispositivo_id: Annotated[str, Query(description="Dispositivo a consultar (UUID).")],
    use_case: Annotated[ExportarCargasUseCase, Depends(get_exportar_cargas_use_case)],
    desde: datetime | None = None,
    hasta: datetime | None = None,
    dias: Annotated[int, Query(ge=1, le=365)] = 30,
    solo_no_atribuidos: bool = False,
):
    try:
        stream = use_case.ejecutar(
            dispositivo_id=dispositivo_id,
            desde=desde,
            hasta=hasta,
            dias=dias,
            solo_no_atribuidos=solo_no_atribuidos,
        )
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"cargas_{dispositivo_id}_{ts}.csv"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(stream, media_type="text/csv; charset=utf-8", headers=headers)
    except Exception as e:
        manejar_error_http(e)

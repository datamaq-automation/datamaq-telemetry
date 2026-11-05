"""src/infrastructure/fastapi/routes/sge_router.py."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from src.adapters.gateways.in_memory_documentacion_sge_repository import (
    InMemoryDocumentacionSgeRepository,
)
from src.adapters.gateways.in_memory_registro_capacitaciones_sge_repository import (
    InMemoryRegistroCapacitacionesSgeRepository,
)
from src.application.dtos.sge_dto import (
    AcuseCapacitacionRequestDTO,
    AhorrosCusumResponseDTO,
    BalanceEnergiaResponseDTO,
    CostoEstimadoResponseDTO,
    EstadoCompetenciasUsuarioDTO,
    FacturaDistribuidoraResponseDTO,
    LineaBaseResponseDTO,
    RegistroCapacitacionResponseDTO,
    SgeDocArticleDTO,
)
from src.application.mappers.sge_mapper import (
    articulo_to_dto,
    estado_to_dto,
    registro_to_dto,
)
from src.application.use_cases.consultar_ahorros_cusum import (
    ConsultarAhorrosCusumUseCase,
)
from src.application.use_cases.consultar_balance_energia import (
    ConsultarBalanceEnergiaUseCase,
)
from src.application.use_cases.consultar_competencias_usuario import (
    ConsultarCompetenciasUsuarioUseCase,
)
from src.application.use_cases.consultar_costo_estimado import (
    ConsultarCostoEstimadoUseCase,
)
from src.application.use_cases.consultar_documentacion_sge import (
    ConsultarDocumentacionSgeUseCase,
)
from src.application.use_cases.consultar_historico_facturas import (
    ConsultarHistoricoFacturasUseCase,
)
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.application.use_cases.registrar_acuse_capacitacion import (
    RegistrarAcuseCapacitacionUseCase,
)
from src.domain.sge.ports import (
    RepositorioDocumentacionSgePort,
    RepositorioRegistroCapacitacionesSgePort,
)
from src.domain.telemetria.ports import RepositorioOrganizacionesPort, RepositorioTelemetriaPort
from src.infrastructure.fastapi.dependencies import (
    get_repositorio_telemetria,
    get_telemetria_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http
from src.infrastructure.fastapi.planta_ownership import resolver_planta_permitida
from src.infrastructure.yaml.repositories.organizaciones_repository import (
    YamlOrganizacionesRepository,
)

_repositorio_sge_singleton: RepositorioDocumentacionSgePort = InMemoryDocumentacionSgeRepository()
_repositorio_capacitaciones_singleton: RepositorioRegistroCapacitacionesSgePort = (
    InMemoryRegistroCapacitacionesSgeRepository()
)
_repositorio_organizaciones_singleton: RepositorioOrganizacionesPort = YamlOrganizacionesRepository()


def get_documentacion_sge_repository() -> RepositorioDocumentacionSgePort:
    return _repositorio_sge_singleton


def get_registro_capacitaciones_repository() -> RepositorioRegistroCapacitacionesSgePort:
    return _repositorio_capacitaciones_singleton


def get_organizaciones_repository() -> RepositorioOrganizacionesPort:
    return _repositorio_organizaciones_singleton


def get_consultar_documentacion_sge_use_case(
    repo: Annotated[
        RepositorioDocumentacionSgePort,
        Depends(get_documentacion_sge_repository),
    ],
) -> ConsultarDocumentacionSgeUseCase:
    return ConsultarDocumentacionSgeUseCase(repositorio=repo)


def get_registrar_acuse_use_case(
    repo_doc: Annotated[
        RepositorioDocumentacionSgePort,
        Depends(get_documentacion_sge_repository),
    ],
    repo_cap: Annotated[
        RepositorioRegistroCapacitacionesSgePort,
        Depends(get_registro_capacitaciones_repository),
    ],
) -> RegistrarAcuseCapacitacionUseCase:
    return RegistrarAcuseCapacitacionUseCase(
        repo_documentacion=repo_doc,
        repo_capacitaciones=repo_cap,
    )


def get_consultar_competencias_use_case(
    repo_doc: Annotated[
        RepositorioDocumentacionSgePort,
        Depends(get_documentacion_sge_repository),
    ],
    repo_cap: Annotated[
        RepositorioRegistroCapacitacionesSgePort,
        Depends(get_registro_capacitaciones_repository),
    ],
) -> ConsultarCompetenciasUsuarioUseCase:
    return ConsultarCompetenciasUsuarioUseCase(
        repo_documentacion=repo_doc,
        repo_capacitaciones=repo_cap,
    )


def get_consultar_balance_use_case(
    repo_org: Annotated[
        RepositorioOrganizacionesPort,
        Depends(get_organizaciones_repository),
    ],
) -> ConsultarBalanceEnergiaUseCase:
    return ConsultarBalanceEnergiaUseCase(repo_organizaciones=repo_org)


def get_consultar_ahorros_use_case(
    repo_org: Annotated[
        RepositorioOrganizacionesPort,
        Depends(get_organizaciones_repository),
    ],
) -> ConsultarAhorrosCusumUseCase:
    return ConsultarAhorrosCusumUseCase(repo_organizaciones=repo_org)


def get_consultar_historico_facturas_use_case(
    repo_org: Annotated[
        RepositorioOrganizacionesPort,
        Depends(get_organizaciones_repository),
    ],
) -> ConsultarHistoricoFacturasUseCase:
    return ConsultarHistoricoFacturasUseCase(repo_organizaciones=repo_org)


def get_consultar_costo_estimado_use_case(
    repo_org: Annotated[
        RepositorioOrganizacionesPort,
        Depends(get_organizaciones_repository),
    ],
    repo_telemetria: Annotated[
        RepositorioTelemetriaPort,
        Depends(get_repositorio_telemetria),
    ],
    consultar_telemetria: Annotated[
        ConsultarTelemetriaUseCase,
        Depends(get_telemetria_use_case),
    ],
) -> ConsultarCostoEstimadoUseCase:
    return ConsultarCostoEstimadoUseCase(
        repo_organizaciones=repo_org,
        repo_telemetria=repo_telemetria,
        consultar_telemetria=consultar_telemetria,
    )


router = APIRouter(
    prefix="/api/v1/sge",
    tags=["SGE - ISO 50001"],
    dependencies=[Depends(get_usuario_actual)],
)


@router.get(
    "/documentacion",
    response_model=list[SgeDocArticleDTO],
    response_model_by_alias=True,
    summary="Consultar documentación operativa SGE según el rol del usuario autenticado",
)
def obtener_documentacion_sge(
    use_case: Annotated[
        ConsultarDocumentacionSgeUseCase,
        Depends(get_consultar_documentacion_sge_use_case),
    ],
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    rol: str | None = Query(
        None,
        description="Previsualizar documentación como otro rol (permitido para administradores)",
    ),
) -> list[SgeDocArticleDTO]:
    """Retorna los procedimientos, instructivos y políticas del SGE ISO 50001 correspondientes."""
    try:
        rol_usuario = str(claims.get("rol", "operador"))
        articulos = use_case.ejecutar(rol_usuario=rol_usuario, rol_filtro=rol)
        return [articulo_to_dto(a) for a in articulos]
    except Exception as exc:
        manejar_error_http(exc)


@router.post(
    "/competencias/acuse",
    response_model=RegistroCapacitacionResponseDTO,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar acuse y evidencia de capacitación o toma de conciencia (ISO 50001 §7.2)",
)
def registrar_acuse_capacitacion(
    dto: AcuseCapacitacionRequestDTO,
    use_case: Annotated[
        RegistrarAcuseCapacitacionUseCase,
        Depends(get_registrar_acuse_use_case),
    ],
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
) -> RegistroCapacitacionResponseDTO:
    """Registra de forma inmutable la evidencia de capacitación del usuario autenticado."""
    try:
        usuario_id = str(claims.get("sub", ""))
        rol_usuario = str(claims.get("rol", "operador"))
        registro = use_case.ejecutar(
            usuario_id=usuario_id,
            articulo_id=dto.articulo_id,
            rol_usuario=rol_usuario,
            version_doc=dto.version_doc,
            comentarios=dto.comentarios,
        )
        return registro_to_dto(registro)
    except Exception as exc:
        manejar_error_http(exc)


@router.get(
    "/competencias/mis-capacitaciones",
    response_model=EstadoCompetenciasUsuarioDTO,
    response_model_by_alias=True,
    summary="Consultar estado de competencias y capacitaciones pendientes (ISO 50001 §7.2)",
)
def consultar_mis_competencias(
    use_case: Annotated[
        ConsultarCompetenciasUsuarioUseCase,
        Depends(get_consultar_competencias_use_case),
    ],
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
) -> EstadoCompetenciasUsuarioDTO:
    """Retorna el consolidado de capacitaciones completadas, pendientes y porcentaje de cumplimiento."""
    try:
        usuario_id = str(claims.get("sub", ""))
        rol_usuario = str(claims.get("rol", "operador"))
        estado = use_case.ejecutar(usuario_id=usuario_id, rol_usuario=rol_usuario)
        return estado_to_dto(estado)
    except Exception as exc:
        manejar_error_http(exc)


@router.get(
    "/plantas/{planta_id}/balance-energia",
    dependencies=[Depends(resolver_planta_permitida)],
    response_model=BalanceEnergiaResponseDTO,
    response_model_by_alias=True,
    summary="Consultar balance de energía en TGBT y pérdidas técnicas (ISO 50001 §6.3)",
)
def obtener_balance_energia(
    planta_id: str,
    use_case: Annotated[
        ConsultarBalanceEnergiaUseCase,
        Depends(get_consultar_balance_use_case),
    ],
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    nodo_id: str | None = Query(None, description="Nodo de cabecera (TGBT o Trafo)"),
    energia_padre_kwh: float | None = Query(None, description="Energía registrada en cabecera (kWh)"),
    energias_hijos_kwh: list[float] | None = Query(None, description="Energías de subcircuitos (kWh)"),
    thd_i_promedio_pct: float | None = Query(None, description="Distorsión armónica en corriente promedio (%)"),
) -> BalanceEnergiaResponseDTO:
    """Evalúa la conciliación del balance en el unifilar y detecta pérdidas elevadas o justificación por armónicos."""
    try:
        return use_case.ejecutar(
            planta_id=planta_id,
            nodo_id=nodo_id,
            energia_padre_kwh=energia_padre_kwh,
            energias_hijos_kwh=energias_hijos_kwh,
            thd_i_promedio_pct=thd_i_promedio_pct,
        )
    except Exception as exc:
        manejar_error_http(exc)


@router.get(
    "/plantas/{planta_id}/ahorros-cusum",
    dependencies=[Depends(resolver_planta_permitida)],
    response_model=AhorrosCusumResponseDTO,
    response_model_by_alias=True,
    summary="Consultar ahorros acumulados y curva CUSUM frente a EnB congelada (ISO 50006 / ISO 50001 §9.1)",
)
def obtener_ahorros_cusum(
    planta_id: str,
    use_case: Annotated[
        ConsultarAhorrosCusumUseCase,
        Depends(get_consultar_ahorros_use_case),
    ],
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    unidades_producidas: float = Query(..., ge=0.0, description="Volumen o unidades de producción en el período"),
    horas_periodo: float = Query(..., gt=0.0, description="Duración del período en horas"),
    energia_real_kwh: float = Query(..., ge=0.0, description="Energía activa real consumida (kWh)"),
    linea_base_id: str | None = Query(None, description="Identificador de la EnB congelada (opcional)"),
) -> AhorrosCusumResponseDTO:
    """Calcula ahorros de energía auditables y la serie temporal CUSUM frente a la EnB congelada en GitOps."""
    try:
        return use_case.ejecutar(
            planta_id=planta_id,
            unidades_producidas=unidades_producidas,
            horas_periodo=horas_periodo,
            energia_real_kwh=energia_real_kwh,
            linea_base_id=linea_base_id,
        )
    except Exception as exc:
        manejar_error_http(exc)


@router.get(
    "/plantas/{planta_id}/linea-base",
    dependencies=[Depends(resolver_planta_permitida)],
    response_model=list[LineaBaseResponseDTO],
    response_model_by_alias=True,
    summary="Consultar Líneas de Base Energética (EnB) congeladas en GitOps para la planta (ISO 50001 §6.5)",
)
def obtener_lineas_base(
    planta_id: str,
    repo_org: Annotated[
        RepositorioOrganizacionesPort,
        Depends(get_organizaciones_repository),
    ],
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
) -> list[LineaBaseResponseDTO]:
    """Retorna las Líneas de Base Energética congeladas y auditables declaradas en data/organizaciones.yml."""
    try:
        lbs = repo_org.obtener_lineas_base_planta(planta_id)
        return [
            LineaBaseResponseDTO(
                id=str(lb["id"]),
                nombre=str(lb.get("nombre", "EnB")),
                nodo_id=str(lb.get("nodo_id", "")),
                nodo_nombre=str(lb.get("nodo_nombre", "")),
                sec_referencia_kwh_unidad=float(lb.get("sec_referencia_kwh_unidad", 0.0)),
                potencia_base_kw=float(lb.get("potencia_base_kw", 0.0)),
                periodo_referencia_desde=str(lb.get("periodo_referencia_desde", "")),
                periodo_referencia_hasta=str(lb.get("periodo_referencia_hasta", "")),
                congelada_en=str(lb.get("congelada_en", "")),
                autorizado_por=lb.get("autorizado_por"),
                activa=bool(lb.get("activa", True)),
                tolerancia_perdidas_pct=float(lb.get("tolerancia_perdidas_pct", 0.04)),
            )
            for lb in lbs
        ]
    except Exception as exc:
        manejar_error_http(exc)


@router.get(
    "/plantas/{planta_id}/facturas-distribuidora",
    dependencies=[Depends(resolver_planta_permitida)],
    response_model=list[FacturaDistribuidoraResponseDTO],
    response_model_by_alias=True,
    summary="Consultar el histórico de facturas de la distribuidora de la planta (ISO 50001 §6.3 / §9.1)",
)
def obtener_facturas_distribuidora(
    planta_id: str,
    use_case: Annotated[
        ConsultarHistoricoFacturasUseCase,
        Depends(get_consultar_historico_facturas_use_case),
    ],
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
) -> list[FacturaDistribuidoraResponseDTO]:
    """Retorna el histórico de facturas mensuales de la distribuidora (`data/facturas_distribuidora.yml`),
    orden descendente por período."""
    try:
        return use_case.ejecutar(planta_id=planta_id)
    except Exception as exc:
        manejar_error_http(exc)


@router.get(
    "/plantas/{planta_id}/costo-estimado",
    dependencies=[Depends(resolver_planta_permitida)],
    response_model=CostoEstimadoResponseDTO,
    response_model_by_alias=True,
    summary="Costo estimado en pesos del período de facturación en curso (ISO 50001 §6.3 / §9.1)",
)
def obtener_costo_estimado(
    planta_id: str,
    use_case: Annotated[
        ConsultarCostoEstimadoUseCase,
        Depends(get_consultar_costo_estimado_use_case),
    ],
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    nodo_id: str | None = Query(
        None, description="Nodo del unifilar a costear; por defecto, el TGBT/transformador principal"
    ),
) -> CostoEstimadoResponseDTO:
    """Componente de energía calculado con datos en vivo del período en curso x `$/kWh` promedio
    de la última factura real. Componente de potencia siempre "s/d" (`costoPotenciaArs=null`):
    requiere tracking de demanda máxima en vivo, no implementado todavía."""
    try:
        return use_case.ejecutar(planta_id=planta_id, nodo_id=nodo_id)
    except Exception as exc:
        manejar_error_http(exc)

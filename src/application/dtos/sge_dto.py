"""src/application/dtos/sge_dto.py."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CategoriaSgeDTO = Literal[
    "politica",
    "operacion",
    "mantenimiento",
    "normativa_enre",
    "metas_enpi",
]


class SgeDocArticleDTO(BaseModel):
    id: str
    titulo: str
    categoria: CategoriaSgeDTO
    roles_permitidos: list[str] = Field(alias="rolesPermitidos")
    resumen: str
    puntos_clave: list[str] = Field(alias="puntosClave")
    acciones_inmediatas: list[str] = Field(alias="accionesInmediatas")
    referencia_iso: str = Field(alias="referenciaIso")
    documento_url: str | None = Field(default=None, alias="documentoUrl")

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class AcuseCapacitacionRequestDTO(BaseModel):
    articulo_id: str = Field(alias="articuloId")
    version_doc: str = Field(alias="versionDoc")
    comentarios: str | None = None

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class RegistroCapacitacionResponseDTO(BaseModel):
    id: str
    usuario_id: str = Field(alias="usuarioId")
    articulo_id: str = Field(alias="articuloId")
    rol_usuario: str = Field(alias="rolUsuario")
    fecha_completado: str = Field(alias="fechaCompletado")
    version_doc: str = Field(alias="versionDoc")
    comentarios: str | None = None

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class EstadoCompetenciasUsuarioDTO(BaseModel):
    usuario_id: str = Field(alias="usuarioId")
    rol_usuario: str = Field(alias="rolUsuario")
    capacitaciones_completadas: list[RegistroCapacitacionResponseDTO] = Field(alias="capacitacionesCompletadas")
    capacitaciones_pendientes: list[SgeDocArticleDTO] = Field(alias="capacitacionesPendientes")
    porcentaje_cumplimiento: float = Field(alias="porcentajeCumplimiento")

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class BalanceEnergiaResponseDTO(BaseModel):
    planta_id: str = Field(alias="plantaId")
    nodo_padre_id: str = Field(alias="nodoPadreId")
    nodo_padre_nombre: str = Field(alias="nodoPadreNombre")
    energia_padre_kwh: float = Field(alias="energiaPadreKwh")
    energia_hijos_sumada_kwh: float = Field(alias="energiaHijosSumadaKwh")
    residual_kwh: float = Field(alias="residualKwh")
    residual_porcentual: float = Field(alias="residualPorcentual")
    estado: str
    es_auditable_iso50001: bool = Field(alias="esAuditableIso50001")
    detalle: str
    thd_i_promedio_pct: float | None = Field(default=None, alias="thdIPromedioPct")

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class PuntoCusumDTO(BaseModel):
    fecha: str
    energia_real_kwh: float = Field(alias="energiaRealKwh")
    energia_esperada_kwh: float = Field(alias="energiaEsperadaKwh")
    ahorro_kwh: float = Field(alias="ahorroKwh")
    cusum_acumulado_kwh: float = Field(alias="cusumAcumuladoKwh")

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class AhorrosCusumResponseDTO(BaseModel):
    planta_id: str = Field(alias="plantaId")
    linea_base_id: str = Field(alias="lineaBaseId")
    linea_base_nombre: str = Field(alias="lineaBaseNombre")
    ahorro_total_kwh: float = Field(alias="ahorroTotalKwh")
    ahorro_porcentual: float = Field(alias="ahorroPorcentual")
    es_mejora: bool = Field(alias="esMejora")
    detalle: str
    puntos_cusum: list[PuntoCusumDTO] = Field(default_factory=list, alias="puntosCusum")

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class LineaBaseResponseDTO(BaseModel):
    id: str
    nombre: str
    nodo_id: str = Field(alias="nodoId")
    nodo_nombre: str = Field(alias="nodoNombre")
    sec_referencia_kwh_unidad: float = Field(alias="secReferenciaKwhUnidad")
    potencia_base_kw: float = Field(alias="potenciaBaseKw")
    periodo_referencia_desde: str = Field(alias="periodoReferenciaDesde")
    periodo_referencia_hasta: str = Field(alias="periodoReferenciaHasta")
    congelada_en: str = Field(alias="congeladaEn")
    autorizado_por: str | None = Field(default=None, alias="autorizadoPor")
    activa: bool = True
    tolerancia_perdidas_pct: float = Field(default=0.04, alias="toleranciaPerdidasPct")

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )

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
    planta_id: str = Field(validation_alias="plantaId", serialization_alias="plantaId")
    nodo_padre_id: str = Field(validation_alias="nodoPadreId", serialization_alias="nodoPadreId")
    nodo_padre_nombre: str = Field(validation_alias="nodoPadreNombre", serialization_alias="nodoPadreNombre")
    energia_padre_kwh: float = Field(validation_alias="energiaPadreKwh", serialization_alias="energiaPadreKwh")
    energia_hijos_sumada_kwh: float = Field(
        validation_alias="energiaHijosSumadaKwh", serialization_alias="energiaHijosSumadaKwh"
    )
    residual_kwh: float = Field(validation_alias="residualKwh", serialization_alias="residualKwh")
    residual_porcentual: float = Field(validation_alias="residualPorcentual", serialization_alias="residualPorcentual")
    estado: str
    es_auditable_iso50001: bool = Field(
        validation_alias="esAuditableIso50001", serialization_alias="esAuditableIso50001"
    )
    detalle: str
    thd_i_promedio_pct: float | None = Field(
        default=None, validation_alias="thdIPromedioPct", serialization_alias="thdIPromedioPct"
    )

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class PuntoCusumDTO(BaseModel):
    fecha: str
    energia_real_kwh: float = Field(validation_alias="energiaRealKwh", serialization_alias="energiaRealKwh")
    energia_esperada_kwh: float = Field(validation_alias="energiaEsperadaKwh", serialization_alias="energiaEsperadaKwh")
    ahorro_kwh: float = Field(validation_alias="ahorroKwh", serialization_alias="ahorroKwh")
    cusum_acumulado_kwh: float = Field(validation_alias="cusumAcumuladoKwh", serialization_alias="cusumAcumuladoKwh")

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class AhorrosCusumResponseDTO(BaseModel):
    planta_id: str = Field(validation_alias="plantaId", serialization_alias="plantaId")
    linea_base_id: str = Field(validation_alias="lineaBaseId", serialization_alias="lineaBaseId")
    linea_base_nombre: str = Field(validation_alias="lineaBaseNombre", serialization_alias="lineaBaseNombre")
    ahorro_total_kwh: float = Field(validation_alias="ahorroTotalKwh", serialization_alias="ahorroTotalKwh")
    ahorro_porcentual: float = Field(validation_alias="ahorroPorcentual", serialization_alias="ahorroPorcentual")
    es_mejora: bool = Field(validation_alias="esMejora", serialization_alias="esMejora")
    detalle: str
    puntos_cusum: list[PuntoCusumDTO] = Field(
        default_factory=list, validation_alias="puntosCusum", serialization_alias="puntosCusum"
    )

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class FacturaDistribuidoraResponseDTO(BaseModel):
    """Un documento de facturación (potencia O energía) — ver FacturaDistribuidora en domain/sge.

    Dos filas con el mismo `periodo` pueden coexistir con `tipoDato` distinto (potencia de un
    proveedor, energía de otro): el consumidor decide si las combina o las grafica por separado.
    """

    id: str
    planta_id: str = Field(validation_alias="plantaId", serialization_alias="plantaId")
    periodo: str
    proveedor: str
    tipo_dato: str = Field(validation_alias="tipoDato", serialization_alias="tipoDato")
    numero_factura: str = Field(validation_alias="numeroFactura", serialization_alias="numeroFactura")
    importe_total_ars: float = Field(validation_alias="importeTotalArs", serialization_alias="importeTotalArs")
    tarifa: str | None = None
    dias_facturados: int | None = Field(
        default=None, validation_alias="diasFacturados", serialization_alias="diasFacturados"
    )
    energia_activa_punta_kwh: float | None = Field(
        default=None, validation_alias="energiaActivaPuntaKwh", serialization_alias="energiaActivaPuntaKwh"
    )
    energia_activa_resto_kwh: float | None = Field(
        default=None, validation_alias="energiaActivaRestoKwh", serialization_alias="energiaActivaRestoKwh"
    )
    energia_activa_valle_kwh: float | None = Field(
        default=None, validation_alias="energiaActivaValleKwh", serialization_alias="energiaActivaValleKwh"
    )
    energia_activa_total_kwh: float | None = Field(
        default=None, validation_alias="energiaActivaTotalKwh", serialization_alias="energiaActivaTotalKwh"
    )
    energia_facturada_kwh: float | None = Field(
        default=None, validation_alias="energiaFacturadaKwh", serialization_alias="energiaFacturadaKwh"
    )
    potencia_contratada_punta_kw: float | None = Field(
        default=None, validation_alias="potenciaContratadaPuntaKw", serialization_alias="potenciaContratadaPuntaKw"
    )
    potencia_contratada_fuera_punta_kw: float | None = Field(
        default=None,
        validation_alias="potenciaContratadaFueraPuntaKw",
        serialization_alias="potenciaContratadaFueraPuntaKw",
    )
    potencia_adquirida_punta_kw: float | None = Field(
        default=None, validation_alias="potenciaAdquiridaPuntaKw", serialization_alias="potenciaAdquiridaPuntaKw"
    )
    potencia_adquirida_fuera_punta_kw: float | None = Field(
        default=None,
        validation_alias="potenciaAdquiridaFueraPuntaKw",
        serialization_alias="potenciaAdquiridaFueraPuntaKw",
    )
    potencia_excedida_punta_kw: float | None = Field(
        default=None, validation_alias="potenciaExcedidaPuntaKw", serialization_alias="potenciaExcedidaPuntaKw"
    )
    potencia_excedida_fuera_punta_kw: float | None = Field(
        default=None,
        validation_alias="potenciaExcedidaFueraPuntaKw",
        serialization_alias="potenciaExcedidaFueraPuntaKw",
    )
    importe_potencia_ars: float | None = Field(
        default=None, validation_alias="importePotenciaArs", serialization_alias="importePotenciaArs"
    )
    importe_energia_ars: float | None = Field(
        default=None, validation_alias="importeEnergiaArs", serialization_alias="importeEnergiaArs"
    )
    valor_energia_ars_kwh_promedio: float | None = Field(
        default=None, validation_alias="valorEnergiaArsKwhPromedio", serialization_alias="valorEnergiaArsKwhPromedio"
    )
    energia_registrada_punta_kwh: float | None = Field(
        default=None,
        validation_alias="energiaRegistradaPuntaKwh",
        serialization_alias="energiaRegistradaPuntaKwh",
        description="Energía activa registrada en punta por el medidor de la distribuidora (kWh). No es energía facturada.",
    )
    energia_registrada_resto_kwh: float | None = Field(
        default=None,
        validation_alias="energiaRegistradaRestoKwh",
        serialization_alias="energiaRegistradaRestoKwh",
        description="Energía activa registrada en resto por el medidor de la distribuidora (kWh). No es energía facturada.",
    )
    energia_registrada_valle_kwh: float | None = Field(
        default=None,
        validation_alias="energiaRegistradaValleKwh",
        serialization_alias="energiaRegistradaValleKwh",
        description="Energía activa registrada en valle por el medidor de la distribuidora (kWh). No es energía facturada.",
    )
    energia_registrada_total_kwh: float | None = Field(
        default=None,
        validation_alias="energiaRegistradaTotalKwh",
        serialization_alias="energiaRegistradaTotalKwh",
        description="Total de energía activa registrada impreso en la factura de la distribuidora (kWh). No es energía facturada.",
    )
    energia_reactiva_punta_kvarh: float | None = Field(
        default=None,
        validation_alias="energiaReactivaPuntaKvarh",
        serialization_alias="energiaReactivaPuntaKvarh",
        description="Energía reactiva registrada en punta por el medidor de la distribuidora (kVArh).",
    )
    energia_reactiva_resto_kvarh: float | None = Field(
        default=None,
        validation_alias="energiaReactivaRestoKvarh",
        serialization_alias="energiaReactivaRestoKvarh",
        description="Energía reactiva registrada en resto por el medidor de la distribuidora (kVArh).",
    )
    energia_reactiva_valle_kvarh: float | None = Field(
        default=None,
        validation_alias="energiaReactivaValleKvarh",
        serialization_alias="energiaReactivaValleKvarh",
        description="Energía reactiva registrada en valle por el medidor de la distribuidora (kVArh).",
    )
    # Desglose regulatorio Mercado Eléctrico Mayorista (CAMMESA) — decisión 2026-10-01
    potencia_adquirida_mem_kw: float | None = Field(
        default=None,
        validation_alias="potenciaAdquiridaMemKw",
        serialization_alias="potenciaAdquiridaMemKw",
    )
    importe_potencia_mem_ars: float | None = Field(
        default=None,
        validation_alias="importePotenciaMemArs",
        serialization_alias="importePotenciaMemArs",
    )
    importe_adicionales_mem_ars: float | None = Field(
        default=None,
        validation_alias="importeAdicionalesMemArs",
        serialization_alias="importeAdicionalesMemArs",
    )
    importe_transporte_mem_ars: float | None = Field(
        default=None,
        validation_alias="importeTransporteMemArs",
        serialization_alias="importeTransporteMemArs",
    )
    importe_otros_cargos_mem_ars: float | None = Field(
        default=None,
        validation_alias="importeOtrosCargosMemArs",
        serialization_alias="importeOtrosCargosMemArs",
    )
    importe_neto_ars: float | None = Field(
        default=None,
        validation_alias="importeNetoArs",
        serialization_alias="importeNetoArs",
    )
    importe_impuestos_ars: float | None = Field(
        default=None,
        validation_alias="importeImpuestosArs",
        serialization_alias="importeImpuestosArs",
    )
    valor_energia_integral_ars_kwh: float | None = Field(
        default=None,
        validation_alias="valorEnergiaIntegralArsKwh",
        serialization_alias="valorEnergiaIntegralArsKwh",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class LineaBaseResponseDTO(BaseModel):
    id: str
    nombre: str
    nodo_id: str = Field(validation_alias="nodoId", serialization_alias="nodoId")
    nodo_nombre: str = Field(validation_alias="nodoNombre", serialization_alias="nodoNombre")
    sec_referencia_kwh_unidad: float = Field(
        validation_alias="secReferenciaKwhUnidad", serialization_alias="secReferenciaKwhUnidad"
    )
    potencia_base_kw: float = Field(validation_alias="potenciaBaseKw", serialization_alias="potenciaBaseKw")
    periodo_referencia_desde: str = Field(
        validation_alias="periodoReferenciaDesde", serialization_alias="periodoReferenciaDesde"
    )
    periodo_referencia_hasta: str = Field(
        validation_alias="periodoReferenciaHasta", serialization_alias="periodoReferenciaHasta"
    )
    congelada_en: str = Field(validation_alias="congeladaEn", serialization_alias="congeladaEn")
    autorizado_por: str | None = Field(
        default=None, validation_alias="autorizadoPor", serialization_alias="autorizadoPor"
    )
    activa: bool = True
    tolerancia_perdidas_pct: float = Field(
        default=0.04, validation_alias="toleranciaPerdidasPct", serialization_alias="toleranciaPerdidasPct"
    )

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class CostoEstimadoResponseDTO(BaseModel):
    """Costo estimado en pesos del período de facturación en curso.

    El componente de energía se calcula con datos en vivo (kWh consumidos hasta ahora en el
    período) y el `$/kWh` promedio de la última factura de energía real de la planta. El
    componente de potencia queda explícitamente "s/d" (`costo_potencia_ars=None`): requiere
    tracking de demanda máxima del período en curso sobre datos en vivo, que todavía no existe
    (ver `specs/costo-estimado-periodo-en-curso.md`) — nunca se infiere ni se reemplaza por 0.
    """

    planta_id: str = Field(validation_alias="plantaId", serialization_alias="plantaId")
    periodo_actual: str = Field(validation_alias="periodoActual", serialization_alias="periodoActual")
    kwh_consumido_periodo_actual: float | None = Field(
        default=None,
        validation_alias="kwhConsumidoPeriodoActual",
        serialization_alias="kwhConsumidoPeriodoActual",
    )
    valor_energia_ars_kwh_promedio: float | None = Field(
        default=None,
        validation_alias="valorEnergiaArsKwhPromedio",
        serialization_alias="valorEnergiaArsKwhPromedio",
    )
    costo_energia_ars: float | None = Field(
        default=None, validation_alias="costoEnergiaArs", serialization_alias="costoEnergiaArs"
    )
    periodo_factura_origen: str | None = Field(
        default=None, validation_alias="periodoFacturaOrigen", serialization_alias="periodoFacturaOrigen"
    )
    aviso_tarifa_desactualizada: bool = Field(
        default=False,
        validation_alias="avisoTarifaDesactualizada",
        serialization_alias="avisoTarifaDesactualizada",
    )
    costo_potencia_ars: float | None = Field(
        default=None, validation_alias="costoPotenciaArs", serialization_alias="costoPotenciaArs"
    )
    motivo_potencia_sin_dato: str | None = Field(
        default=None,
        validation_alias="motivoPotenciaSinDato",
        serialization_alias="motivoPotenciaSinDato",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )

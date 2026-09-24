"""src/application/dtos/planta_estructura_dto.py."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.application.dtos.telemetria_dto import EnergiaAgregadaDTO
from src.application.dtos.tipos import FechaHoraUTC
from src.domain.telemetria.servicios.clasificador_nivel_tension import (
    UMBRAL_MEDIA_TENSION_V as UMBRAL_MEDIA_TENSION_V,
)
from src.domain.telemetria.servicios.clasificador_nivel_tension import (
    NivelTension as NivelTensionLiteral,
)
from src.domain.telemetria.servicios.tensiones_de_linea import (
    MagnitudTension as MagnitudTensionLiteral,
)

TipoNodoUnifilarLiteral = Literal["acometida", "transformador", "tgbt", "seccional", "carga"]


class CoordenadasNodoUnifilarDTO(BaseModel):
    x: float
    y: float
    ancho: float | None = None
    orientacion: Literal["horizontal", "vertical"] | None = None
    model_config = ConfigDict(from_attributes=True)


class InterruptorCabeceraDTO(BaseModel):
    tag: str
    tipo: str | None = None
    in_a: float | None = None
    icu_ka: float | None = None
    estado: str = "cerrado"
    model_config = ConfigDict(from_attributes=True, extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _normalizar_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "in_A" in data and "in_a" not in data:
                data["in_a"] = data["in_A"]
            if "icu_kA" in data and "icu_ka" not in data:
                data["icu_ka"] = data["icu_kA"]
        return data


class MetadatosPlacaDTO(BaseModel):
    potencia_nominal_kva: float | None = None
    relacion_tension_kv: str | None = None
    vsc_porcentaje: float | None = None
    grupo_conexion: str | None = None
    corriente_nominal_a: float | None = None
    icw_ka: float | None = None
    frecuencia_hz: float | None = 50.0
    calibre_in_a: float | None = None
    cable_seccion: str | None = None
    longitud_estimada_m: float | None = None
    tension_nominal_v: float | None = None
    categoria_tarifaria: str | None = None
    trafo_asociado_kva: float | None = None
    corriente_barra_a: float | None = None
    proteccion_in_a: float | None = None
    model_config = ConfigDict(from_attributes=True, extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _normalizar_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "corriente_nominal_A" in data and "corriente_nominal_a" not in data:
                data["corriente_nominal_a"] = data["corriente_nominal_A"]
            if "icw_kA" in data and "icw_ka" not in data:
                data["icw_ka"] = data["icw_kA"]
            if "calibre_in_A" in data and "calibre_in_a" not in data:
                data["calibre_in_a"] = data["calibre_in_A"]
        return data


class FaseAgregadaDTO(BaseModel):
    """Magnitudes eléctricas agregadas para una única fase del nodo."""

    voltage_V: float | None = None
    current_A: float | None = None
    net_active_power_W: float | None = None
    net_reactive_power_VAR: float | None = None
    net_apparent_power_VA: float | None = None
    power_factor: float | None = None
    desbalance_tension_pct: float | None = None


class AgregadoPorFaseDTO(BaseModel):
    fase_r: FaseAgregadaDTO
    fase_s: FaseAgregadaDTO
    fase_t: FaseAgregadaDTO
    tension_linea_rs_V: float | None = Field(
        default=None,
        description="Tensión compuesta V_RS (entre fases R y S), derivada de las "
        "fase-neutro suponiendo 120° exactos, en la escala del nodo.",
    )
    tension_linea_st_V: float | None = Field(default=None, description="Tensión compuesta V_ST.")
    tension_linea_tr_V: float | None = Field(default=None, description="Tensión compuesta V_TR.")


class NodoUnifilarDTO(BaseModel):
    id: str
    parent_id: str | None = None
    nombre: str
    tipo: TipoNodoUnifilarLiteral
    device_id: str | None = None
    es_virtual: bool = False
    es_pasante: bool = False
    # R-03: nombre de la máquina asociada 1:1 al medidor (`machines.device_id` UNIQUE), si existe.
    nombre_maquina: str | None = None
    tension_nominal_V: float
    # Derivado de tension_nominal_V contra UMBRAL_MEDIA_TENSION_V; no persistido.
    nivel_tension: NivelTensionLiteral = "BT"
    capacidad_nominal_kVA: float | None = None
    potencia_nominal_kw: float | None = None
    uso_significativo: bool = False
    categoria_uso: str | None = None
    variable_relevante: str | None = None
    orden: int = 0
    fuente_dato: str | None = None
    notas_metrologicas: str | None = None
    coordenadas: CoordenadasNodoUnifilarDTO | None = None
    metadatos_placa: MetadatosPlacaDTO | None = None
    interruptor_cabecera: InterruptorCabeceraDTO | None = None
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class UnifilarPlantaDTO(BaseModel):
    planta_id: str
    nombre_planta: str
    nodos: list[NodoUnifilarDTO] = Field(default_factory=list)
    # True si ArbolUnifilarService.validar() no encontró duplicados, padres colgantes ni ciclos.
    topologia_valida: bool = True
    model_config = ConfigDict(from_attributes=True)


class CoordenadasZonaDTO(BaseModel):
    x_porcentaje: float = Field(ge=0.0, le=100.0)
    y_porcentaje: float = Field(ge=0.0, le=100.0)
    ancho_porcentaje: float = Field(ge=0.0, le=100.0)
    alto_porcentaje: float = Field(ge=0.0, le=100.0)


class ZonaPlantaDTO(BaseModel):
    id: str
    nombre: str
    coordenadas: CoordenadasZonaDTO
    model_config = ConfigDict(from_attributes=True)


class PosicionLayoutDTO(BaseModel):
    x_porcentaje: float = Field(ge=0.0, le=100.0)
    y_porcentaje: float = Field(ge=0.0, le=100.0)


class DispositivoLayoutDTO(BaseModel):
    device_id: str
    zona_id: str | None = None
    posicion: PosicionLayoutDTO
    model_config = ConfigDict(from_attributes=True)


class LayoutPlantaDTO(BaseModel):
    planta_id: str
    nombre_planta: str
    plano_svg_url: str | None = None
    zonas: list[ZonaPlantaDTO] = Field(default_factory=list)
    dispositivos: list[DispositivoLayoutDTO] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class AreaEstadisticasDTO(BaseModel):
    area_id: str
    nombre: str
    superficie_m2: float | None = None
    lineas_count: int = 0
    dispositivos_activos_count: int = 0
    dispositivos_total_count: int = 0
    carga_promedio_kw: float = 0.0
    dispositivo_ids: list[str] = Field(default_factory=list)
    coordenadas_layout: CoordenadasZonaDTO | None = None
    model_config = ConfigDict(from_attributes=True)


class PlantaAreasEstadisticasResponseDTO(BaseModel):
    planta_id: str
    superficie_total_m2: float | None = None
    areas: list[AreaEstadisticasDTO] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class BancoRecomendadoDTO(BaseModel):
    tipo: Literal["banco", "qc"] = "banco"
    potencia_kvar: float
    tension_instalacion_v: float
    justificacion: str


class CompensacionHistoricaDTO(BaseModel):
    periodo_dias: int
    fecha_calculo: FechaHoraUTC
    potencia_reactiva_promedio_kvar: float | None = None
    potencia_reactiva_max_kvar: float | None = None
    potencia_reactiva_min_kvar: float | None = None
    factor_potencia_promedio: float | None = None
    banco_recomendado: BancoRecomendadoDTO | None = None
    sobrecompensacion_sostenida: bool = False


class ResumenNodoUnifilarDTO(BaseModel):
    planta_id: str
    nodo_id: str
    es_virtual: bool
    dispositivos_ids: list[str] = Field(default_factory=list)
    potencia_activa_total_w: float | None = None
    potencia_reactiva_total_var: float | None = None
    potencia_aparente_total_va: float | None = None
    factor_desplazamiento_total: float | None = None
    dispositivos_sin_dato: list[str] = Field(default_factory=list)
    energia_agregada: list[EnergiaAgregadaDTO] = Field(default_factory=list)
    registrado_en: FechaHoraUTC | None = None
    agregado_por_fase: AgregadoPorFaseDTO | None = None
    compensacion_historica: CompensacionHistoricaDTO | None = None
    nivel_tension: NivelTensionLiteral | None = Field(
        default=None,
        description="Nivel de tensión al que está referido `agregado_por_fase` (IEC 60038). "
        "En nodos MT virtuales, el agregado ya viene escalado por la relación de "
        "transformación del nodo (V_MT = V_BT x a); este campo aclara esa escala.",
    )
    tension_nominal_V: float | None = Field(
        default=None,
        description="Tensión nominal entre fases (V_LL) del nodo, en la misma escala que "
        "`agregado_por_fase` (declarada en data/organizaciones.yml).",
    )
    tension_nominal_fase_V: float | None = Field(
        default=None,
        description="Tensión nominal fase-neutro (V_LN): referencia para "
        "agregado_por_fase.fase_r/s/t.voltage_V. None si no se pudo determinar la "
        "cantidad de fases del nodo. En un nodo MT es una referencia a un neutro "
        "virtual (red de 3 conductores, primario en triángulo), no una magnitud "
        "medible en bornes: ver `magnitud_tension_canonica`.",
    )
    magnitud_tension_canonica: MagnitudTensionLiteral | None = Field(
        default=None,
        description="Qué tensión del agregado es la físicamente accesible en este nodo. "
        "'FASE' en BT (estrella con neutro distribuido): usar fase_r/s/t.voltage_V contra "
        "tension_nominal_fase_V. 'LINEA' en MT (3 conductores, primario en triángulo): usar "
        "tension_linea_rs/st/tr_V contra tension_nominal_V.",
    )


class PuntoPotenciaNodoUnifilarDTO(BaseModel):
    momento: FechaHoraUTC
    potencia_activa_total_w: float | None = None
    potencia_reactiva_total_var: float | None = None
    potencia_aparente_total_va: float | None = None
    factor_desplazamiento_total: float | None = None
    dispositivos_sin_dato: list[str] = Field(default_factory=list)


class HistoricoNodoUnifilarDTO(BaseModel):
    """Puntos del nodo más `datos_desde`: el corte de retención más reciente entre sus medidores
    frontera (desde ahí están todos). `None` si el nodo no tiene medidores frontera."""

    puntos: list[PuntoPotenciaNodoUnifilarDTO]
    datos_desde: FechaHoraUTC | None = None

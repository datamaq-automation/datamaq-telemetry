"""src/application/dtos/maquina_dto.py."""

from pydantic import BaseModel, ConfigDict, Field

from src.application.dtos.tipos import FechaHoraUTC
from src.domain.disponibilidad.value_objects import NaturalezaRegimen
from src.domain.maquinas.value_objects import (
    CategoriaCarga,
    EstadoCampana,
    MotivoDescarte,
    NaturalezaElectrica,
    OrigenClasificacionCarga,
    OrigenFirma,
    PatronOperacion,
    TipoCampana,
)


class RegimenOperacionDTO(BaseModel):
    """Segmentación modal de potencia: banda de operación en régimen estacionario."""

    indice: int
    potencia_tipica_w: float
    limite_inferior_w: float
    limite_superior_w: float
    masa: int
    mediana_w: float
    mad_w: float
    persistencia: float
    variacion_mediana_w_s: float
    naturaleza: NaturalezaRegimen


class DiagnosticoConfianzaModalDTO(BaseModel):
    """Diagnóstico de confianza en la segmentación modal."""

    num_modas_estable: int
    fraccion_ventanas_consistentes: float
    es_multimodal_confiable: bool


class DiagnosticoEstacionariedadDTO(BaseModel):
    """Diagnóstico de estacionariedad de la serie."""

    num_subventanas: int
    desplazamiento_maximo_w: float
    desplazamiento_maximo_relativo: float
    es_estacionario: bool


class HistogramaPotenciaResponseDTO(BaseModel):
    """Histograma de frecuencias de potencia con diagnósticos modales."""

    dispositivo_id: str
    dias_analizados: int
    cantidad_lecturas: int
    bordes_bins_w: list[float]
    frecuencias: list[int]
    umbral_sugerido_w: float | None = None
    escala: str = "lineal"
    epsilon_w: float = 0.0
    lecturas_truncadas: bool = False
    lecturas_descartadas: int = 0
    regimenes: list[RegimenOperacionDTO] = Field(default_factory=list)
    diagnostico_modal: DiagnosticoConfianzaModalDTO | None = None
    diagnostico_estacionariedad: DiagnosticoEstacionariedadDTO | None = None


class FirmaMáquinaDTO(BaseModel):
    """Qué buscar en la serie agregada para reconocer esta máquina."""

    potencia_w: float
    dispersion_w: float = 0.0
    potencia_reactiva_var: float | None = None
    factor_potencia: float | None = None
    duracion_encendido_s: float | None = None
    duracion_encendido_mad_s: float | None = None
    duracion_apagado_s: float | None = None
    pico_arranque_w: float | None = None
    origen: OrigenFirma = OrigenFirma.CHAPA
    muestras: int = 0
    medida_en: FechaHoraUTC | None = None
    es_resistiva: bool = False
    esta_completa: bool = False


class MáquinaBaseDTO(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=120)
    dispositivo_id: str


class MáquinaCreateDTO(MáquinaBaseDTO):
    categoria: CategoriaCarga = CategoriaCarga.OTROS
    naturaleza_electrica: NaturalezaElectrica = NaturalezaElectrica.MIXTA
    potencia_nominal_w: float | None = Field(None, gt=0.0)


class MáquinaUpdateDTO(BaseModel):
    nombre: str | None = Field(None, min_length=1, max_length=120)
    categoria: CategoriaCarga | None = None
    naturaleza_electrica: NaturalezaElectrica | None = None
    patron_operacion: PatronOperacion | None = None
    potencia_nominal_w: float | None = Field(None, gt=0.0)
    activa: bool | None = None


class FirmaManualRequestDTO(BaseModel):
    """Fijar una firma a mano, sin campaña. Es el escape para calibración manual."""

    potencia_w: float = Field(..., gt=0.0)
    dispersion_w: float = Field(0.0, ge=0.0)
    potencia_reactiva_var: float | None = None
    factor_potencia: float | None = Field(None, ge=-1.0, le=1.0)
    duracion_encendido_s: float | None = Field(None, gt=0.0)
    duracion_apagado_s: float | None = Field(None, gt=0.0)


class MáquinaResponseDTO(MáquinaBaseDTO):
    id: str
    categoria: CategoriaCarga
    naturaleza_electrica: NaturalezaElectrica
    patron_operacion: PatronOperacion
    potencia_nominal_w: float | None = None
    potencia_esperada_w: float | None = None
    firma: FirmaMáquinaDTO | None = None
    esta_caracterizada: bool
    activa: bool
    creado_en: FechaHoraUTC
    actualizado_en: FechaHoraUTC
    model_config = ConfigDict(from_attributes=True)


class EstadisticaCiclosDTO(BaseModel):
    """Cuánto prende y cuánto descansa una banda de potencia, y qué tan regular es."""

    ciclos: int
    duracion_encendido_mediana_s: float | None = None
    duracion_encendido_mad_s: float | None = None
    duracion_apagado_mediana_s: float | None = None
    duracion_apagado_mad_s: float | None = None
    periodo_mediano_s: float | None = None
    duty_cycle: float | None = None
    patron: PatronOperacion = PatronOperacion.INDETERMINADO
    es_regular: bool = False
    cadencia_mediana_s: float | None = None


class PerfilLineaBaseDTO(BaseModel):
    linea_base_W: float | None = None
    linea_base_nocturna_W: float | None = None
    linea_base_diurna_W: float | None = None
    delta_diurno_W: float | None = None
    potencia_media_W: float | None = None
    potencia_maxima_W: float | None = None
    muestras: int = 0
    ventanas_nocturnas: int = 0
    ventanas_diurnas: int = 0
    cadencia_mediana_s: float | None = None


class PerfilConsumoResponseDTO(BaseModel):
    """Lo que se puede afirmar de un medidor agregado sin ninguna firma calibrada.

    `advertencia_cadencia` no es decorativo: a 300 s hay cargas que el hardware nunca
    midió, y el consumidor de este contrato tiene que poder distinguir "no hubo" de
    "no se pudo ver".
    """

    dispositivo_id: str
    desde: FechaHoraUTC
    hasta: FechaHoraUTC
    dias_analizados: int
    zona_horaria: str
    cantidad_lecturas: int
    lecturas_truncadas: bool = False
    linea_base: PerfilLineaBaseDTO
    ciclos_sobre_linea_base: EstadisticaCiclosDTO
    umbral_ciclos_W: float | None = None
    regimenes: list[RegimenOperacionDTO] = Field(default_factory=list)
    advertencia_cadencia: str | None = None


class EnsayoCreateDTO(BaseModel):
    """Apertura de una campaña de caracterización sobre un medidor."""

    dispositivo_id: str
    duracion_segundos: int = Field(..., ge=60, le=21_600)
    carga_id: str | None = None
    notas: str | None = None


class ResultadoCalibracionDTO(BaseModel):
    estado: EstadoCampana
    motivo: MotivoDescarte | None = None
    detalle: str | None = None
    linea_base_W: float | None = None
    linea_base_VAR: float | None = None
    muestras_analizadas: int = 0
    muestras_en_regimen: int = 0
    dispersion_relativa: float | None = None
    cadencia_mediana_s: float | None = None
    firma: FirmaMáquinaDTO | None = None


class EnsayoResponseDTO(BaseModel):
    id: str
    dispositivo_id: str
    carga_id: str | None = None
    tipo: TipoCampana
    estado: EstadoCampana
    inicio_at: FechaHoraUTC
    fin_planificado_at: FechaHoraUTC
    fin_at: FechaHoraUTC | None = None
    duracion_planificada_s: float
    linea_base_W: float | None = None
    linea_base_VAR: float | None = None
    muestras: int = 0
    motivo_descarte: MotivoDescarte | None = None
    notas: str | None = None
    rafaga_solicitada: bool | None = None
    resultado: ResultadoCalibracionDTO | None = None
    model_config = ConfigDict(from_attributes=True)


class IntervaloActividadResponseDTO(BaseModel):
    id: int | None = None
    dispositivo_id: str
    carga_id: str | None = None
    inicio_at: FechaHoraUTC
    fin_at: FechaHoraUTC
    duracion_segundos: float
    potencia_media_W: float | None = None
    delta_reactiva_VAR: float | None = None
    energia_kwh: float | None = None
    confianza: float | None = None
    origen: OrigenClasificacionCarga = OrigenClasificacionCarga.REGLA
    esta_atribuido: bool = False
    corregido_por_usuario_id: str | None = None
    corregido_at: FechaHoraUTC | None = None
    notas: str | None = None
    model_config = ConfigDict(from_attributes=True)


class CorregirIntervaloRequestDTO(BaseModel):
    """Reimputación manual de un intervalo. `carga_id` nulo lo marca como no atribuido."""

    carga_id: str | None = None
    notas: str | None = None


class ItemAtribucionDTO(BaseModel):
    carga_id: str | None = None
    nombre: str
    energia_kwh: float
    porcentaje: float
    intervalos: int
    confianza_media: float | None = None


class AtribucionConsumoResponseDTO(BaseModel):
    """Reparto del consumo del período, con el residual como resultado de primera clase."""

    dispositivo_id: str
    desde: FechaHoraUTC
    hasta: FechaHoraUTC
    energia_total_kwh: float | None = None
    energia_atribuida_kwh: float = 0.0
    residual_kwh: float | None = None
    residual_porcentaje: float | None = None
    items: list[ItemAtribucionDTO] = Field(default_factory=list)
    calidad_suficiente: bool = False
    advertencia: str | None = None


class AnalisisConsumoResponseDTO(BaseModel):
    dispositivo_id: str
    desde: FechaHoraUTC
    hasta: FechaHoraUTC
    cantidad_lecturas: int
    umbral_escalon_W: float | None = None
    episodios_detectados: int = 0
    intervalos_escritos: int = 0
    atribuidos: int = 0
    no_atribuidos: int = 0
    cargas_con_firma: int = 0
    advertencia_cadencia: str | None = None


class ResumenPropuestaDTO(BaseModel):
    """Resumen de la propuesta de firmas inferidas."""

    dispositivo_id: str
    actualizadas: list[str] = Field(default_factory=list)
    creadas: list[str] = Field(default_factory=list)
    protegidas: list[str] = Field(default_factory=list)
    descartadas: int = 0

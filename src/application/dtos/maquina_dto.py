"""src/application/dtos/maquina_dto.py."""

from pydantic import BaseModel, ConfigDict, Field

from src.application.dtos.tipos import FechaHoraUTC
from src.domain.disponibilidad.value_objects import NaturalezaRegimen


class MaquinaBaseDTO(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=120)
    dispositivo_id: str


class MaquinaCreateDTO(MaquinaBaseDTO):
    pass


class MaquinaUpdateDTO(BaseModel):
    nombre: str | None = Field(None, min_length=1, max_length=120)
    umbral_marcha_w: float | None = Field(None, ge=0.0)
    ventana_persistencia_lecturas: int | None = Field(None, ge=1)
    ventana_persistencia_segundos: float | None = Field(None, ge=0.0)


class MaquinaResponseDTO(MaquinaBaseDTO):
    id: str
    umbral_marcha_w: float | None = None
    ventana_persistencia_lecturas: int
    ventana_persistencia_segundos: float
    esta_calibrada: bool
    creado_en: FechaHoraUTC
    actualizado_en: FechaHoraUTC
    model_config = ConfigDict(from_attributes=True)


class RegimenOperacionDTO(BaseModel):
    indice: int
    potencia_tipica_w: float
    limite_inferior_w: float
    limite_superior_w: float
    masa: float
    mediana_w: float
    mad_w: float
    persistencia: float
    variacion_mediana_w_s: float | None = None
    naturaleza: NaturalezaRegimen = NaturalezaRegimen.INDETERMINADO


class DiagnosticoConfianzaModalDTO(BaseModel):
    num_modas_estable: int
    fraccion_ventanas_consistentes: float
    es_multimodal_confiable: bool


class DiagnosticoEstacionariedadDTO(BaseModel):
    num_subventanas: int
    desplazamiento_maximo_w: float | None = None
    desplazamiento_maximo_relativo: float | None = None
    es_estacionario: bool


class HistogramaPotenciaResponseDTO(BaseModel):
    dispositivo_id: str
    dias_analizados: int
    cantidad_lecturas: int
    bordes_bins_w: list[float]
    frecuencias: list[int]
    umbral_sugerido_w: float | None = None
    escala: str = "logaritmica"
    epsilon_w: float = 0.0
    lecturas_truncadas: bool = False
    lecturas_descartadas: int = 0
    regimenes: list[RegimenOperacionDTO] = Field(default_factory=list)
    diagnostico_modal: DiagnosticoConfianzaModalDTO | None = None
    diagnostico_estacionariedad: DiagnosticoEstacionariedadDTO | None = None


class MaquinaInferidaDTO(BaseModel):
    """Máquina propuesta por energy-ml para un dispositivo."""

    id: str = Field(..., description="UUID de la máquina inferida")
    nombre: str = Field(..., min_length=1, max_length=120, description="Nombre propuesto por ML")
    tipo_maquina: str = Field(..., description="Tipo: motor, compresor, bomba, etc.")
    confianza: float = Field(..., ge=0.0, le=1.0, description="Score del modelo [0.0, 1.0]")
    patrones_detectados: list[str] = Field(default_factory=list, description="Ej: armónicos, arranque-suave")
    energia_kwh_mes: float = Field(..., ge=0.0, description="Consumo estimado mes")
    costo_estimado_ars: float = Field(..., ge=0.0, description="Costo estimado mes")
    model_config = ConfigDict(from_attributes=True)


class ListaMaquinasInferidaDTO(BaseModel):
    """Respuesta: máquinas propuestas por ML para dispositivo."""

    dispositivo_id: str
    maquinas_inferidas: list[MaquinaInferidaDTO] = Field(default_factory=list)
    ultima_ejecucion_ml: FechaHoraUTC | None = None
    total_confianza_prom: float = Field(default=0.0, ge=0.0, le=1.0)
    model_config = ConfigDict(from_attributes=True)

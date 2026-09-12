"""src/domain/disponibilidad/value_objects.py."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class EstadoMaquina(str, Enum):
    MARCHA = "MARCHA"
    PARADA = "PARADA"


class TipoParada(str, Enum):
    PROGRAMADA = "PROGRAMADA"
    NO_PROGRAMADA = "NO_PROGRAMADA"
    SIN_CLASIFICAR = "SIN_CLASIFICAR"


class OrigenClasificacion(str, Enum):
    REGLA = "REGLA"
    CORRECCION_HUMANA = "CORRECCION_HUMANA"


class NaturalezaRegimen(str, Enum):
    """Por qué un régimen tiene la masa que tiene.

    La distribución marginal de potencia no distingue dos causas muy distintas de baja
    densidad: un régimen por el que la máquina *pasa rápido* (transitorio) y uno que
    simplemente *se usa poco* pero es estable. Solo la dinámica temporal (|ΔP|/Δt)
    las separa; sin serie temporal, o con una cadencia demasiado gruesa para sostener
    la afirmación, corresponde `INDETERMINADO` y no una clasificación sin respaldo.
    """

    ESTABLE = "ESTABLE"
    TRANSITORIO = "TRANSITORIO"
    INDETERMINADO = "INDETERMINADO"


@dataclass(frozen=True)
class RegimenOperacion:
    """Un modo de la distribución de potencia: una "potencia típica" y su banda.

    Los límites son las *antimodas* (valles) que separan este régimen de sus vecinos.
    `masa`, `mediana_w` y `mad_w` se calculan sobre las lecturas crudas de la banda,
    no sobre los bins, para no arrastrar el error de discretización.
    """

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


@dataclass(frozen=True)
class DiagnosticoConfianzaModal:
    """Cuánta confianza merece la estructura modal hallada.

    El número de modas es monótono no creciente en el ancho de suavizado: una estructura
    que sobrevive a un rango amplio de anchos es real; una que solo aparece en una ventana
    angosta es ruido de muestreo. `fraccion_ventanas_consistentes` mide esa supervivencia.
    """

    num_modas_estable: int
    fraccion_ventanas_consistentes: float
    es_multimodal_confiable: bool


@dataclass(frozen=True)
class DiagnosticoEstacionariedad:
    """Si las modas se sostienen a lo largo de la ventana analizada o se corren.

    Un histograma de 90 días mezcla regímenes que cambiaron (mix de producto, desgaste)
    y funde campanas distintas en una sola ancha y falsa.
    """

    num_subventanas: int
    desplazamiento_maximo_relativo: float | None
    desplazamiento_maximo_w: float | None
    es_estacionario: bool


@dataclass(frozen=True)
class SegmentacionPotencia:
    """Resultado completo de segmentar la potencia histórica de una máquina."""

    bordes_bins_w: list[float]
    """Longitud `len(frecuencias) + 1`. Los bins son de **ancho variable** (escala log):
    el consumidor no puede inferir el último borde asumiendo espaciado uniforme."""

    frecuencias: list[int]
    regimenes: list[RegimenOperacion]
    epsilon_w: float
    lecturas_analizadas: int
    lecturas_no_positivas: int
    diagnostico_modal: DiagnosticoConfianzaModal | None = None
    diagnostico_estacionariedad: DiagnosticoEstacionariedad | None = None
    cadencia_mediana_s: float | None = None
    escala: str = "logaritmica"

    @property
    def lecturas_descartadas(self) -> int:
        return self.lecturas_no_positivas

    @property
    def umbral_marcha_sugerido_w(self) -> float | None:
        """Frontera parada↔marcha: la antimoda más baja.

        `EstadoMaquina` es binario y PARADA es, por definición, el régimen de menor
        potencia: todo lo que quede por encima de la primera antimoda es marcha. No se
        elige la antimoda de mayor persistencia porque en una máquina con
        standby / marcha-baja / marcha-alta esa frontera puede caer *dentro* de marcha
        y partirla al medio.

        Contracara conocida: si una máquina tiene dos niveles de reposo distintos
        (standby bajo y standby alto), esta frontera separa los dos reposos en vez de
        reposo-vs-marcha. Eso no se puede resolver solo con la distribución.
        """
        if len(self.regimenes) < 2:
            return None
        return round(self.regimenes[0].limite_superior_w, 2)


@dataclass(frozen=True)
class MetricasDisponibilidadOEE:
    """Métricas de disponibilidad industrial (OEE / TPM) inferidas de la telemetría."""

    periodo_inicio: datetime
    periodo_fin: datetime
    tiempo_total_s: float
    tiempo_marcha_s: float
    tiempo_parada_programada_s: float
    tiempo_parada_no_programada_s: float
    disponibilidad_oee_pct: float
    mtbf_horas: float | None = None
    mttr_horas: float | None = None
    cantidad_paradas_no_programadas: int = 0
    cantidad_paradas_programadas: int = 0
    cantidad_ciclos_marcha: int = 0

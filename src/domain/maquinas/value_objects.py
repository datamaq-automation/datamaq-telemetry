"""src/domain/maquinas/value_objects.py."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class CategoriaCarga(str, Enum):
    """Para qué se usa la carga. Agrupa el reporte de consumo; no afecta la detección."""

    REFRIGERACION = "REFRIGERACION"
    COCCION = "COCCION"
    CALENTAMIENTO_AGUA = "CALENTAMIENTO_AGUA"
    LAVADO = "LAVADO"
    ILUMINACION = "ILUMINACION"
    CLIMATIZACION = "CLIMATIZACION"
    FUERZA_MOTRIZ = "FUERZA_MOTRIZ"
    OTROS = "OTROS"


class NaturalezaElectrica(str, Enum):
    """Cómo consume la carga, que es lo que la potencia reactiva puede ver.

    Una resistencia pura (pava, horno, termotanque) toma Q≈0 y FP≈1. Un motor
    (heladera, freezer, lavarropas) toma Q significativa y FP 0.5-0.8. Esa diferencia
    es el eje que `EmparejadorFirmasService` usa para separar familias de cargas, y
    sale gratis porque `total_reactive_power` ya se persiste en cada lectura.
    """

    RESISTIVA = "RESISTIVA"
    MOTOR = "MOTOR"
    ELECTRONICA = "ELECTRONICA"
    MIXTA = "MIXTA"


class PatronOperacion(str, Enum):
    """Cómo se reparte en el tiempo el encendido de la carga.

    Es la dimensión que pide el análisis de "período de funcionamiento y de
    inactividad", y la única que separa entre sí a las cargas resistivas de potencia
    parecida (pava, anafe, horno y termotanque son indistinguibles por ΔP y ΔQ).
    """

    CICLICO_TERMOSTATICO = "CICLICO_TERMOSTATICO"
    MANUAL_PULSO = "MANUAL_PULSO"
    MANUAL_PROLONGADO = "MANUAL_PROLONGADO"
    PROGRAMADO_SECUENCIAL = "PROGRAMADO_SECUENCIAL"
    CONTINUO_DIARIO = "CONTINUO_DIARIO"
    INDETERMINADO = "INDETERMINADO"


class OrigenClasificacionCarga(str, Enum):
    """Quién decidió a qué carga pertenece un intervalo.

    Mismo vocabulario que `OrigenClasificacion` de disponibilidad, y por la misma razón:
    distinguir lo que dijo una regla de lo que confirmó una persona es lo que convierte
    al historial en un dataset etiquetado.
    """

    REGLA = "REGLA"
    CORRECCION_HUMANA = "CORRECCION_HUMANA"


class OrigenFirma(str, Enum):
    """De dónde salió la firma, que es lo que dice cuánto confiar en ella.

    `CHAPA` es la potencia nominal declarada por el usuario: sirve de arranque en frío
    pero miente (la nominal no es la de régimen y no dice nada de la duración).
    `CAMPANA` es medida sobre el equipo real. `INFERIDA` la dedujo el motor del
    histórico sin confirmación humana.
    """

    CHAPA = "CHAPA"
    CAMPANA = "CAMPANA"
    INFERIDA = "INFERIDA"


@dataclass(frozen=True)
class FirmaCarga:
    """Qué tiene que ver el motor en la serie agregada para reconocer esta carga.

    No alcanza con la potencia: `duracion_encendido_s` es lo que distingue una pava
    (2-4 min) de un termotanque (20-60 min) cuando ambos son ~1800 W resistivos. Por
    eso una firma sin duración es una firma a medias, y `esta_completa` lo declara.
    """

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
    medida_en: datetime | None = None

    UMBRAL_FP_RESISTIVA = 0.95

    @property
    def es_resistiva(self) -> bool:
        """`None` cuenta como no resistiva: sin FP medido no se afirma nada."""
        return self.factor_potencia is not None and self.factor_potencia >= self.UMBRAL_FP_RESISTIVA

    @property
    def esta_completa(self) -> bool:
        """Una firma sirve para desambiguar solo si trae potencia *y* duración.

        La dispersión no entra en la cuenta a propósito: una carga perfectamente estable
        mide MAD cero, y eso la hace más confiable, no menos. Quien la consume acota la
        banda con un piso propio.
        """
        return self.duracion_encendido_s is not None and self.potencia_w > 0.0


@dataclass(frozen=True)
class CicloOperacion:
    """Un tramo continuo en que la carga estuvo por encima de su umbral de encendido.

    `duracion_apagado_previa_s` mira hacia atrás, hacia el hueco que separa este ciclo
    del anterior: es la mitad "inactividad" del par que describe una carga cíclica.
    """

    inicio: datetime
    fin: datetime
    duracion_encendido_s: float
    duracion_apagado_previa_s: float | None
    potencia_media_w: float
    muestras: int


@dataclass(frozen=True)
class EstadisticaCiclos:
    """Resumen del ciclado de una carga: cuánto prende, cuánto descansa y qué tan regular es.

    Las dispersiones van como MAD y no como desvío estándar por la misma razón que en
    `SegmentadorRegimenesService`: un solo ciclo anómalo (una puerta de heladera abierta
    diez minutos) no debe redefinir la regularidad de todo el conjunto.
    """

    ciclos: int
    duracion_encendido_mediana_s: float | None
    duracion_encendido_mad_s: float | None
    duracion_apagado_mediana_s: float | None
    duracion_apagado_mad_s: float | None
    periodo_mediano_s: float | None
    duty_cycle: float | None
    patron: PatronOperacion = PatronOperacion.INDETERMINADO
    cadencia_mediana_s: float | None = None

    @property
    def es_regular(self) -> bool:
        """Regular = las duraciones de encendido no se dispersan más de un tercio de su mediana."""
        if self.duracion_encendido_mediana_s is None or self.duracion_encendido_mad_s is None:
            return False
        if self.duracion_encendido_mediana_s <= 0:
            return False
        return (self.duracion_encendido_mad_s / self.duracion_encendido_mediana_s) < 0.35


@dataclass(frozen=True)
class PerfilLineaBase:
    """Cuánto consume la casa (o la planta) cuando nadie hace nada.

    `linea_base_nocturna_w` se mide en la franja en que solo quedan encendidas las
    cargas autónomas —refrigeración y standby—, y es el estimador más confiable que
    una cadencia gruesa puede dar.

    `delta_diurno_w` es la diferencia contra la franja diurna. **No es "iluminación"**:
    es todo lo que se suma de día y no se puede separar en escalones a esta cadencia
    (iluminación, electrónica, cargas breves). Se reporta así, sin bautizarlo.
    """

    linea_base_w: float | None
    linea_base_nocturna_w: float | None
    linea_base_diurna_w: float | None
    delta_diurno_w: float | None
    potencia_media_w: float | None
    potencia_maxima_w: float | None
    muestras: int
    ventanas_nocturnas: int
    ventanas_diurnas: int
    cadencia_mediana_s: float | None = None


class TipoCampana(str, Enum):
    """Cómo se aísla la carga durante la medición.

    `ACTIVA` sirve para lo que se puede prender a voluntad (pava, horno, lavarropas):
    se mide la línea de base, se prende, y la diferencia es la carga.

    `PASIVA` existe porque una heladera no se prende cuando uno quiere: se apaga todo
    lo demás y se observa un rato largo, dejando que el termostato haga su ciclo. Es
    también el único camino para un termotanque, que arranca cuando se le enfría el agua.
    """

    ACTIVA = "ACTIVA"
    PASIVA = "PASIVA"


class EstadoCampana(str, Enum):
    """`CONTAMINADA` no es un error del sistema: es el resultado honesto de una medición
    en la que se prendió algo más y por lo tanto no describe a la carga que se quería medir.
    Se informa como tal y se pide repetirla, en vez de emitir una firma sucia."""

    EN_CURSO = "EN_CURSO"
    COMPLETADA = "COMPLETADA"
    CONTAMINADA = "CONTAMINADA"
    DESCARTADA = "DESCARTADA"


class MotivoDescarte(str, Enum):
    SIN_MUESTRAS = "SIN_MUESTRAS"
    SIN_LINEA_BASE = "SIN_LINEA_BASE"
    SIN_ENCENDIDO_DETECTADO = "SIN_ENCENDIDO_DETECTADO"
    DISPERSION_EXCESIVA = "DISPERSION_EXCESIVA"
    ESCALON_AJENO = "ESCALON_AJENO"
    CICLOS_INSUFICIENTES = "CICLOS_INSUFICIENTES"


@dataclass(frozen=True)
class MuestraCampana:
    """Una lectura de alta resolución capturada durante una campaña.

    Trae la fila eléctrica completa y no solo P porque el objetivo de la campaña es
    justamente medir la firma entera: Q y FP son los que después separan un motor de
    una resistencia en la serie gruesa de 5 minutos.
    """

    momento: datetime
    potencia_w: float
    potencia_reactiva_var: float | None = None
    potencia_aparente_va: float | None = None
    factor_potencia: float | None = None
    tension_v: float | None = None
    corriente_a: float | None = None


@dataclass(frozen=True)
class ResultadoCalibracion:
    """Qué salió de una campaña, incluida la posibilidad de que no saliera nada.

    `firma` es `None` siempre que `estado` no sea `COMPLETADA`: no se emite una firma
    a medias con una advertencia al lado, porque aguas abajo la advertencia se pierde
    y la firma se usa igual.
    """

    estado: EstadoCampana
    firma: FirmaCarga | None = None
    motivo: MotivoDescarte | None = None
    linea_base_w: float | None = None
    linea_base_var: float | None = None
    muestras_analizadas: int = 0
    muestras_en_regimen: int = 0
    dispersion_relativa: float | None = None
    cadencia_mediana_s: float | None = None
    detalle: str | None = None


@dataclass(frozen=True)
class EscalonPotencia:
    """Un salto neto entre dos muestras consecutivas: una carga que entró o salió.

    Guarda `delta_reactiva_var` además de `delta_w` porque el par (ΔP, ΔQ) es el espacio
    de firmas clásico de NILM: separa una resistencia (ΔQ≈0) de un motor (ΔQ alta) sin
    saber nada más de la carga.
    """

    momento: datetime
    delta_w: float
    delta_reactiva_var: float | None
    potencia_previa_w: float
    potencia_posterior_w: float

    @property
    def es_encendido(self) -> bool:
        return self.delta_w > 0


@dataclass(frozen=True)
class EpisodioCarga:
    """Un encendido emparejado con su apagado: algo estuvo prendido entre estos instantes.

    Es la unidad que se intenta atribuir a una carga del catálogo. Un escalón suelto,
    sin su contraparte, no llega a episodio: no se sabe cuánto duró y la duración es la
    mitad de la identidad.
    """

    inicio: datetime
    fin: datetime
    delta_w: float
    delta_reactiva_var: float | None
    duracion_s: float
    potencia_media_w: float
    muestras: int
    dispersion_w: float | None = None
    factor_potencia: float | None = None

    @property
    def energia_kwh(self) -> float:
        return round(self.potencia_media_w * self.duracion_s / 3_600_000.0, 6)

    @property
    def ratio_reactiva(self) -> float | None:
        """|ΔQ/ΔP|. Cerca de 0 es resistivo; por encima de ~0.3 hay motor."""
        if self.delta_reactiva_var is None or self.delta_w == 0:
            return None
        return abs(self.delta_reactiva_var / self.delta_w)


@dataclass(frozen=True)
class DiagnosticoReglasCarga:
    """Diagnóstico emitido por el clasificador determinista de reglas físicas."""

    aparato_sugerido: str
    categoria: CategoriaCarga
    naturaleza_electrica: NaturalezaElectrica
    confianza: float
    reglas_aplicadas: tuple[str, ...]
    es_ambiguo: bool = False
    alternativas: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidatoAtribucion:
    """Una carga que podría explicar un episodio, con su puntaje y por qué."""

    maquina_id: str
    nombre: str
    score: float
    factor_potencia_score: float
    factor_reactiva_score: float
    factor_duracion_score: float
    factor_horario_score: float


@dataclass(frozen=True)
class DecisionAtribucion:
    """A qué carga se le imputa un episodio, o por qué a ninguna.

    `maquina_id is None` es un resultado de primera clase y no un fallo: a esta cadencia
    hay cargas que el hardware nunca midió, y una atribución equivocada envenena el
    dataset etiquetado que después alimenta cualquier modelo.
    """

    maquina_id: str | None
    confianza: float
    motivo: str
    candidatos: list[CandidatoAtribucion]


@dataclass(frozen=True)
class ItemAtribucion:
    maquina_id: str | None
    nombre: str
    energia_kwh: float
    porcentaje: float
    intervalos: int
    confianza_media: float | None = None


@dataclass(frozen=True)
class AtribucionConsumo:
    """Reparto del consumo de un período entre las cargas conocidas, más el residual.

    `energia_total_kwh` sale del contador acumulado, que es exacto. No se integra la
    serie instantánea de 5 minutos: entre muestra y muestra puede haber prendido y
    apagado cualquier cosa, y esa integral sería sistemáticamente sesgada.
    """

    desde: datetime
    hasta: datetime
    energia_total_kwh: float | None
    energia_atribuida_kwh: float
    residual_kwh: float | None
    residual_porcentaje: float | None
    items: list[ItemAtribucion]
    calidad_suficiente: bool
    advertencia: str | None = None


@dataclass(frozen=True)
class MáquinaInferida:
    """Máquina que un descubridor externo encontró en la serie agregada (ya en W)."""

    potencia_w: float
    dispersion_w: float
    encendidos: int
    apagados: int
    ciclos_por_dia: float | None
    on_off: bool

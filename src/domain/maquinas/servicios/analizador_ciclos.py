"""src/domain/maquinas/servicios/analizador_ciclos.py — Ciclado de una carga: cuánto tiempo prende, cuánto descansa y con qué regularidad."""

from dataclasses import replace
from datetime import datetime

from src.domain.maquinas.servicios.estadistica import (
    cadencia_mediana_segundos,
    desviacion_absoluta_mediana,
    dispersion_relativa,
    mediana,
)
from src.domain.maquinas.value_objects import (
    CicloOperacion,
    EstadisticaCiclos,
    PatronOperacion,
)
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal

_SIN_CICLOS = EstadisticaCiclos(
    ciclos=0,
    duracion_encendido_mediana_s=None,
    duracion_encendido_mad_s=None,
    duracion_apagado_mediana_s=None,
    duracion_apagado_mad_s=None,
    periodo_mediano_s=None,
    duty_cycle=None,
)


class AnalizadorCiclosService:
    """Extrae los tramos de encendido de una banda de potencia y los caracteriza.

    Responde la pregunta que el histograma no puede: el histograma dice *cuánta masa*
    hay en cada nivel de potencia, pero descarta el orden temporal, y por lo tanto no
    distingue una carga que prende veinte veces por diez minutos de otra que prende una
    vez por tres horas. Esa diferencia es justamente lo que separa una heladera de un
    termotanque, y solo vive en la serie.

    **Límite de cadencia, explícito:** un ciclo más corto que la cadencia de muestreo
    no existe para este servicio. A 300 s no se puede afirmar nada sobre un encendido
    de 2 minutos, y por eso `MIN_MUESTRAS_ENCENDIDO` exige que el tramo se sostenga en
    más de una muestra antes de contarlo como ciclo.
    """

    MIN_LECTURAS = 20
    MIN_MUESTRAS_ENCENDIDO = 2
    """Un tramo de una sola muestra es indistinguible de un pico espurio."""

    FACTOR_HUECO_CADENCIA = 3.0
    """Mismo criterio que `SegmentadorRegimenesService`: un salto mayor a este múltiplo
    de la cadencia es un hueco de datos y corta el ciclo en vez de prolongarlo."""

    MIN_CICLOS_PERIODICIDAD = 6
    DISPERSION_MAXIMA_ENCENDIDO = 0.35
    DISPERSION_MAXIMA_PERIODO = 0.40
    DUTY_CYCLE_CONTINUO = 0.90
    FACTOR_PULSO_CADENCIA = 2.0
    FACTOR_PROLONGADO_CADENCIA = 4.0

    @classmethod
    def extraer_ciclos(
        cls,
        lecturas: list[LecturaPotenciaTemporal],
        umbral_encendido_w: float,
        umbral_apagado_w: float | None = None,
    ) -> list[CicloOperacion]:
        """Tramos continuos por encima del umbral, con histéresis opcional.

        `umbral_apagado_w` por debajo de `umbral_encendido_w` da histéresis: evita que
        una carga que oscila justo en la frontera genere una ráfaga de ciclos falsos.
        Sin él, ambos umbrales coinciden.
        """
        if len(lecturas) < 2:
            return []

        umbral_bajo = umbral_apagado_w if umbral_apagado_w is not None else umbral_encendido_w
        cadencia = cadencia_mediana_segundos([lectura.momento for lectura in lecturas])
        hueco_maximo = (cadencia or 0.0) * cls.FACTOR_HUECO_CADENCIA

        ciclos: list[CicloOperacion] = []
        tramo: list[LecturaPotenciaTemporal] = []
        fin_anterior: datetime | None = None
        anterior: LecturaPotenciaTemporal | None = None

        for lectura in lecturas:
            hay_hueco = (
                anterior is not None
                and hueco_maximo > 0
                and (lectura.momento - anterior.momento).total_seconds() > hueco_maximo
            )
            if hay_hueco and tramo:
                fin_anterior = cls._cerrar(tramo, ciclos, fin_anterior, cadencia)
                tramo = []

            encendida = lectura.potencia_w >= umbral_encendido_w if not tramo else lectura.potencia_w >= umbral_bajo
            if encendida:
                tramo.append(lectura)
            elif tramo:
                fin_anterior = cls._cerrar(tramo, ciclos, fin_anterior, cadencia)
                tramo = []
            anterior = lectura

        if tramo:
            cls._cerrar(tramo, ciclos, fin_anterior, cadencia)
        return ciclos

    @classmethod
    def _cerrar(
        cls,
        tramo: list[LecturaPotenciaTemporal],
        ciclos: list[CicloOperacion],
        fin_anterior: datetime | None,
        cadencia: float | None,
    ) -> datetime | None:
        """Convierte un tramo en ciclo si tiene sustento, y devuelve el nuevo fin previo.

        La duración se extiende una cadencia más allá de la última muestra: la carga
        siguió encendida durante el intervalo que la muestra representa, no se apagó
        exactamente en el instante en que fue medida.
        """
        if len(tramo) < cls.MIN_MUESTRAS_ENCENDIDO:
            return fin_anterior

        inicio = tramo[0].momento
        fin = tramo[-1].momento
        duracion = (fin - inicio).total_seconds() + (cadencia or 0.0)
        apagado_previo = (inicio - fin_anterior).total_seconds() if fin_anterior is not None else None

        ciclos.append(
            CicloOperacion(
                inicio=inicio,
                fin=fin,
                duracion_encendido_s=round(duracion, 1),
                duracion_apagado_previa_s=round(apagado_previo, 1) if apagado_previo is not None else None,
                potencia_media_w=round(sum(t.potencia_w for t in tramo) / len(tramo), 2),
                muestras=len(tramo),
            )
        )
        return fin

    @classmethod
    def _duty_cycle(
        cls, lecturas: list[LecturaPotenciaTemporal], encendidos: list[float], cadencia: float | None
    ) -> float | None:
        """Fracción de la ventana observada en que la carga estuvo encendida.

        Se mide contra el lapso total de la serie y no contra la suma de encendidos y
        reposos detectados: una carga que nunca se apaga tiene un solo ciclo y ningún
        reposo, y con la otra fórmula su duty cycle sería indefinido justo en el caso
        en que vale 1.
        """
        lapso = (lecturas[-1].momento - lecturas[0].momento).total_seconds() + (cadencia or 0.0)
        if lapso <= 0:
            return None
        return round(min(sum(encendidos) / lapso, 1.0), 4)

    @classmethod
    def _inferir_patron(
        cls,
        encendidos: list[float],
        periodos: list[float],
        duty_cycle: float | None,
        cadencia: float | None,
    ) -> PatronOperacion:
        """Traduce las estadísticas a un patrón, o admite `INDETERMINADO`.

        Se prefiere no clasificar antes que clasificar sin respaldo, igual que hace
        `NaturalezaRegimen.INDETERMINADO` en el segmentador de regímenes: un patrón
        inventado se propaga después como una atribución de consumo equivocada.
        """
        mediana_on = mediana(encendidos)
        if mediana_on is None or cadencia is None:
            return PatronOperacion.INDETERMINADO

        if duty_cycle is not None and duty_cycle >= cls.DUTY_CYCLE_CONTINUO:
            return PatronOperacion.CONTINUO_DIARIO

        dispersion_on = dispersion_relativa(encendidos)
        dispersion_periodo = dispersion_relativa(periodos)
        es_ciclica = (
            len(encendidos) >= cls.MIN_CICLOS_PERIODICIDAD
            and dispersion_on is not None
            and dispersion_on < cls.DISPERSION_MAXIMA_ENCENDIDO
            and dispersion_periodo is not None
            and dispersion_periodo < cls.DISPERSION_MAXIMA_PERIODO
        )
        if es_ciclica:
            return PatronOperacion.CICLICO_TERMOSTATICO

        if mediana_on <= cadencia * cls.FACTOR_PULSO_CADENCIA:
            return PatronOperacion.MANUAL_PULSO
        if mediana_on >= cadencia * cls.FACTOR_PROLONGADO_CADENCIA:
            return PatronOperacion.MANUAL_PROLONGADO
        return PatronOperacion.INDETERMINADO

    @classmethod
    def analizar(
        cls,
        lecturas: list[LecturaPotenciaTemporal],
        umbral_encendido_w: float,
        umbral_apagado_w: float | None = None,
    ) -> EstadisticaCiclos:
        """Punto de entrada del servicio: ciclos + su resumen estadístico."""
        if len(lecturas) < cls.MIN_LECTURAS:
            return _SIN_CICLOS

        cadencia = cadencia_mediana_segundos([lectura.momento for lectura in lecturas])
        ciclos = cls.extraer_ciclos(lecturas, umbral_encendido_w, umbral_apagado_w)
        if not ciclos:
            return replace(_SIN_CICLOS, cadencia_mediana_s=cadencia)

        encendidos = [c.duracion_encendido_s for c in ciclos]
        apagados = [c.duracion_apagado_previa_s for c in ciclos if c.duracion_apagado_previa_s is not None]
        # Un período completo es el reposo previo más el encendido que lo sigue. Se arma
        # desde cada ciclo y no apareando dos listas: el primer ciclo no tiene reposo
        # previo, y un hueco de datos puede dejar otros sin él.
        periodos = [
            c.duracion_apagado_previa_s + c.duracion_encendido_s
            for c in ciclos
            if c.duracion_apagado_previa_s is not None
        ]

        duty = cls._duty_cycle(lecturas, encendidos, cadencia)

        return EstadisticaCiclos(
            ciclos=len(ciclos),
            duracion_encendido_mediana_s=mediana(encendidos),
            duracion_encendido_mad_s=desviacion_absoluta_mediana(encendidos),
            duracion_apagado_mediana_s=mediana(apagados),
            duracion_apagado_mad_s=desviacion_absoluta_mediana(apagados),
            periodo_mediano_s=mediana(periodos),
            duty_cycle=duty,
            patron=cls._inferir_patron(encendidos, periodos, duty, cadencia),
            cadencia_mediana_s=cadencia,
        )

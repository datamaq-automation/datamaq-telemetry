"""src/domain/cargas/servicios/detector_escalones.py — Detección de escalones de potencia y su emparejado en episodios."""

import itertools

from src.domain.cargas.servicios.estadistica import (
    cadencia_mediana_segundos,
    desviacion_absoluta_mediana,
    percentil,
)
from src.domain.cargas.value_objects import EpisodioCarga, EscalonPotencia
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal


class DetectorEscalonesService:
    """Encuentra los saltos netos de la serie y los aparea en encendidos con su apagado.

    El umbral de escalón **se calibra del ruido de la propia serie** (MAD de los ΔP) en
    vez de fijarse en un valor absoluto: la misma constante que en un domicilio dejaría
    pasar todo, en un tablero industrial de 200 kW no detectaría nada.

    A cadencia de 5 minutos esto encuentra pocos episodios y es lo esperado: los valles
    de la serie casi no contienen transiciones, contienen regímenes desocupados. Un
    encendido más corto que el intervalo de muestreo no dejó ningún par de muestras del
    que deducir un escalón, y el servicio no lo inventa.
    """

    MIN_LECTURAS = 20
    FACTOR_HUECO_CADENCIA = 3.0
    """Mismo criterio que `SegmentadorRegimenesService`: un par separado por más de este
    múltiplo de la cadencia es un hueco de datos, no una transición."""

    FACTOR_MAD_UMBRAL = 6.0
    FACTOR_P75_UMBRAL = 1.5
    """Respaldo cuando la MAD degenera. La MAD de los ΔP vale cero en cuanto más de la
    mitad de los saltos son idénticos —una señal muy regular, o una serie casi plana con
    unos pocos escalones—, y ahí el umbral colapsaría al piso absoluto: en un tablero de
    200 kW eso convertiría cada ondulación en un escalón. El percentil 75 no se anula
    mientras haya alguna variación y escala con la señal."""

    PISO_ESCALON_W = 40.0
    TOLERANCIA_APAREO = 0.35
    """Cuánto puede diferir el apagado del encendido en magnitud y seguir siendo el mismo
    episodio. Amplio a propósito: la potencia de una carga deriva mientras funciona."""

    DURACION_MAXIMA_EPISODIO_S = 21_600.0
    """Seis horas. Más que cualquier ciclo de una carga doméstica o de una máquina, y
    por lo tanto un emparejado espurio: el apagado real se perdió (un hueco de datos, un
    escalón por debajo del umbral) y el encendido terminó apareándose con el de otra
    carga horas después."""

    @classmethod
    def _pares_validos(
        cls, lecturas: list[LecturaPotenciaTemporal], cadencia: float | None
    ) -> list[tuple[LecturaPotenciaTemporal, LecturaPotenciaTemporal]]:
        limite = (cadencia or 0.0) * cls.FACTOR_HUECO_CADENCIA
        return [
            (a, b)
            for a, b in itertools.pairwise(lecturas)
            if limite <= 0 or 0 < (b.momento - a.momento).total_seconds() <= limite
        ]

    @classmethod
    def umbral_escalon(cls, lecturas: list[LecturaPotenciaTemporal]) -> float:
        """Cuánto tiene que saltar la potencia para no ser ruido de la propia señal."""
        cadencia = cadencia_mediana_segundos([lectura.momento for lectura in lecturas])
        deltas = [abs(b.potencia_w - a.potencia_w) for a, b in cls._pares_validos(lecturas, cadencia)]
        mad = desviacion_absoluta_mediana(deltas) or 0.0
        # El percentil es un *respaldo*, no un término más del máximo: como término
        # dominaría en una serie normal y subiría el umbral hasta tapar cargas chicas
        # (una heladera de 120 W desaparece detrás de un umbral de 148 W). Solo entra
        # cuando la MAD degenera a cero y no hay otra escala de la que agarrarse.
        escala = mad * cls.FACTOR_MAD_UMBRAL
        if escala <= 0:
            escala = (percentil(deltas, 0.75) or 0.0) * cls.FACTOR_P75_UMBRAL
        return max(cls.PISO_ESCALON_W, escala)

    @classmethod
    def detectar(cls, lecturas: list[LecturaPotenciaTemporal], umbral_w: float | None = None) -> list[EscalonPotencia]:
        if len(lecturas) < cls.MIN_LECTURAS:
            return []

        cadencia = cadencia_mediana_segundos([lectura.momento for lectura in lecturas])
        umbral = umbral_w if umbral_w is not None else cls.umbral_escalon(lecturas)

        escalones: list[EscalonPotencia] = []
        for anterior, actual in cls._pares_validos(lecturas, cadencia):
            delta = actual.potencia_w - anterior.potencia_w
            if abs(delta) < umbral:
                continue
            delta_q = None
            if actual.potencia_reactiva_var is not None and anterior.potencia_reactiva_var is not None:
                delta_q = round(actual.potencia_reactiva_var - anterior.potencia_reactiva_var, 2)
            escalones.append(
                EscalonPotencia(
                    momento=actual.momento,
                    delta_w=round(delta, 2),
                    delta_reactiva_var=delta_q,
                    potencia_previa_w=anterior.potencia_w,
                    potencia_posterior_w=actual.potencia_w,
                )
            )
        return escalones

    @classmethod
    def _compatible(cls, encendido: EscalonPotencia, apagado: EscalonPotencia) -> bool:
        return abs(abs(apagado.delta_w) - encendido.delta_w) <= encendido.delta_w * cls.TOLERANCIA_APAREO

    @classmethod
    def _potencia_media(
        cls, lecturas: list[LecturaPotenciaTemporal], inicio_idx: int, fin_idx: int, base_w: float
    ) -> tuple[float, int]:
        tramo = lecturas[inicio_idx:fin_idx]
        if not tramo:
            return 0.0, 0
        return round(sum(t.potencia_w for t in tramo) / len(tramo) - base_w, 2), len(tramo)

    @classmethod
    def emparejar(
        cls, lecturas: list[LecturaPotenciaTemporal], escalones: list[EscalonPotencia]
    ) -> list[EpisodioCarga]:
        """Aparea cada encendido con el apagado compatible más cercano.

        Se recorre con una pila para respetar el anidamiento: si mientras una carga está
        prendida entra otra, el primer apagado compatible corresponde a la última que
        entró, no a la primera.
        """
        indice = {lectura.momento: i for i, lectura in enumerate(lecturas)}
        pendientes: list[EscalonPotencia] = []
        episodios: list[EpisodioCarga] = []

        for escalon in escalones:
            if escalon.es_encendido:
                pendientes.append(escalon)
                continue

            # Un encendido que lleva demasiado tiempo esperando su apagado ya no puede
            # ser el par de nada: se descarta antes de buscar, para que no se aparee con
            # el apagado de otra carga horas más tarde.
            pendientes = [
                p for p in pendientes if (escalon.momento - p.momento).total_seconds() <= cls.DURACION_MAXIMA_EPISODIO_S
            ]
            pareja = next(
                (i for i in range(len(pendientes) - 1, -1, -1) if cls._compatible(pendientes[i], escalon)),
                None,
            )
            if pareja is None:
                continue

            encendido = pendientes.pop(pareja)
            media, muestras = cls._potencia_media(
                lecturas,
                indice.get(encendido.momento, 0),
                indice.get(escalon.momento, 0),
                encendido.potencia_previa_w,
            )
            # Una carga no consume potencia negativa. Si el promedio del tramo cae por
            # debajo de la potencia previa al encendido, lo que pasó es que otras cargas
            # se apagaron en el medio: el par no describe un encendido real.
            if media <= 0:
                continue

            episodios.append(
                EpisodioCarga(
                    inicio=encendido.momento,
                    fin=escalon.momento,
                    delta_w=encendido.delta_w,
                    delta_reactiva_var=encendido.delta_reactiva_var,
                    duracion_s=round((escalon.momento - encendido.momento).total_seconds(), 1),
                    potencia_media_w=media,
                    muestras=muestras,
                )
            )

        return sorted(episodios, key=lambda e: e.inicio)

    @classmethod
    def detectar_episodios(
        cls, lecturas: list[LecturaPotenciaTemporal], umbral_w: float | None = None
    ) -> list[EpisodioCarga]:
        """Punto de entrada del servicio."""
        return cls.emparejar(lecturas, cls.detectar(lecturas, umbral_w))

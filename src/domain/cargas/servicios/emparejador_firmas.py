"""src/domain/cargas/servicios/emparejador_firmas.py — Atribución de un episodio de potencia a una carga del catálogo."""

import math
from datetime import tzinfo

from src.domain.cargas.entities import Carga
from src.domain.cargas.value_objects import (
    CandidatoAtribucion,
    DecisionAtribucion,
    EpisodioCarga,
    FirmaCarga,
    NaturalezaElectrica,
)

_SIN_CANDIDATOS = "Ninguna carga del catálogo tiene firma calibrada."
_BAJO_UMBRAL = "El mejor candidato ({nombre}, {score:.2f}) no alcanza el mínimo de confianza."
_AMBIGUO = "Ambiguo entre {primero} ({s1:.2f}) y {segundo} ({s2:.2f}): las firmas no se separan lo suficiente."


class EmparejadorFirmasService:
    """Puntúa un episodio contra cada carga con firma y decide, o se abstiene.

    El puntaje es el **producto** de cuatro factores en [0,1] y no su promedio: un
    promedio deja que un factor excelente compense a uno que dice explícitamente "esto
    no puede ser". Si la naturaleza eléctrica no cierra, no importa cuán bien coincida
    la potencia.

    Los cuatro factores, y qué problema resuelve cada uno:

    1. **Potencia** — la coincidencia obvia, tolerada por la dispersión medida de la firma.
    2. **Reactiva** — separa familias enteras. Una pava y una heladera nunca se confunden
       porque una toma Q≈0 y la otra no, y eso el medidor ya lo registra.
    3. **Duración** — *el* factor que separa entre sí a los resistivos de potencia
       parecida: pava (2-4 min), anafe (5-30), termotanque (20-60), horno (30-90) son
       indistinguibles por ΔP y por ΔQ, y solo difieren en cuánto duran.
    4. **Horario** — desempate débil por franja del día, cuando la carga lo declara.

    Ante la duda se devuelve `NO_ATRIBUIDO`. Un residual honesto es utilizable; una
    atribución equivocada contamina el dataset etiquetado del que después sale el modelo.
    """

    UMBRAL_MINIMO = 0.35
    RATIO_MINIMO = 1.5
    """Cuánto tiene que superar el primer candidato al segundo para no ser ambiguo."""

    PISO_DISPERSION_W = 25.0
    PISO_DISPERSION_RELATIVA = 0.10
    RATIO_REACTIVA_RESISTIVA = 0.30
    PENALIZACION_NATURALEZA = 0.15
    NEUTRO = 1.0
    """Un factor que no se puede evaluar no premia ni castiga: vale 1 y deja decidir a
    los demás. Inventar un valor sería afirmar algo que no se midió."""

    @staticmethod
    def _gaussiana(distancia: float, escala: float) -> float:
        if escala <= 0:
            return 0.0
        return math.exp(-0.5 * (distancia / escala) ** 2)

    @classmethod
    def _factor_potencia(cls, episodio: EpisodioCarga, firma: FirmaCarga) -> float:
        escala = max(firma.dispersion_w, firma.potencia_w * cls.PISO_DISPERSION_RELATIVA, cls.PISO_DISPERSION_W)
        return cls._gaussiana(abs(episodio.delta_w - firma.potencia_w), escala)

    @classmethod
    def _factor_reactiva(cls, episodio: EpisodioCarga, carga: Carga) -> float:
        """Coherencia entre lo que la carga declara ser y lo que el episodio muestra."""
        ratio = episodio.ratio_reactiva
        if ratio is None:
            return cls.NEUTRO

        parece_resistivo = ratio <= cls.RATIO_REACTIVA_RESISTIVA
        firma = carga.firma
        es_resistiva = (
            firma.es_resistiva
            if firma is not None and firma.factor_potencia is not None
            else carga.naturaleza_electrica == NaturalezaElectrica.RESISTIVA
        )
        if carga.naturaleza_electrica == NaturalezaElectrica.MIXTA and (firma is None or firma.factor_potencia is None):
            return cls.NEUTRO
        return cls.NEUTRO if parece_resistivo == es_resistiva else cls.PENALIZACION_NATURALEZA

    @classmethod
    def _factor_duracion(cls, episodio: EpisodioCarga, firma: FirmaCarga) -> float:
        esperada = firma.duracion_encendido_s
        if esperada is None or esperada <= 0:
            return cls.NEUTRO
        # La escala es multiplicativa: errar 5 minutos en una pava de 3 es fatal, en un
        # horno de 60 es irrelevante.
        escala = max(firma.duracion_encendido_mad_s or 0.0, esperada * 0.5)
        return cls._gaussiana(abs(episodio.duracion_s - esperada), escala)

    @classmethod
    def _factor_horario(cls, episodio: EpisodioCarga, carga: Carga, zona: tzinfo | None) -> float:
        """Sin franjas declaradas por carga, este factor todavía no discrimina."""
        del episodio, carga, zona
        return cls.NEUTRO

    @classmethod
    def puntuar(
        cls, episodio: EpisodioCarga, cargas: list[Carga], zona: tzinfo | None = None
    ) -> list[CandidatoAtribucion]:
        candidatos: list[CandidatoAtribucion] = []
        for carga in cargas:
            if carga.firma is None or not carga.activa:
                continue
            f_p = cls._factor_potencia(episodio, carga.firma)
            f_q = cls._factor_reactiva(episodio, carga)
            f_d = cls._factor_duracion(episodio, carga.firma)
            f_h = cls._factor_horario(episodio, carga, zona)
            candidatos.append(
                CandidatoAtribucion(
                    carga_id=carga.id,
                    nombre=carga.nombre,
                    score=round(f_p * f_q * f_d * f_h, 4),
                    factor_potencia_score=round(f_p, 4),
                    factor_reactiva_score=round(f_q, 4),
                    factor_duracion_score=round(f_d, 4),
                    factor_horario_score=round(f_h, 4),
                )
            )
        return sorted(candidatos, key=lambda c: c.score, reverse=True)

    @classmethod
    def decidir(cls, episodio: EpisodioCarga, cargas: list[Carga], zona: tzinfo | None = None) -> DecisionAtribucion:
        """Punto de entrada del servicio."""
        candidatos = cls.puntuar(episodio, cargas, zona)
        if not candidatos:
            return DecisionAtribucion(None, 0.0, _SIN_CANDIDATOS, [])

        primero = candidatos[0]
        if primero.score < cls.UMBRAL_MINIMO:
            return DecisionAtribucion(
                None,
                primero.score,
                _BAJO_UMBRAL.format(nombre=primero.nombre, score=primero.score),
                candidatos[:3],
            )

        segundo = candidatos[1] if len(candidatos) > 1 else None
        if segundo is not None and segundo.score > 0 and primero.score / segundo.score < cls.RATIO_MINIMO:
            return DecisionAtribucion(
                None,
                primero.score,
                _AMBIGUO.format(primero=primero.nombre, s1=primero.score, segundo=segundo.nombre, s2=segundo.score),
                candidatos[:3],
            )

        return DecisionAtribucion(primero.carga_id, primero.score, f"Atribuido a {primero.nombre}.", candidatos[:3])

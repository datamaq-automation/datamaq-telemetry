"""Partición modal del eje de potencia en regímenes de operación."""

import bisect
import itertools
import math
import statistics

from src.domain.disponibilidad.servicios.dinamica_potencia import (
    clasificar_naturaleza,
    deltas_potencia_validos,
    estimar_cadencia_nominal,
    tasas_de_variacion,
)
from src.domain.disponibilidad.servicios.estacionariedad import (
    evaluar_estacionariedad as _evaluar_estacionariedad_fn,
)
from src.domain.disponibilidad.servicios.histograma_log import (
    construir_bins_log,
    detectar_picos_locales,
    estimar_epsilon,
    percentil,
    suavizar,
)
from src.domain.disponibilidad.servicios.persistencia_modal import (
    antimoda_entre,
    barrer_ancho_banda,
    persistencia_de_modas,
    seleccionar_modas,
)
from src.domain.disponibilidad.value_objects import (
    DiagnosticoEstacionariedad,
    RegimenOperacion,
    SegmentacionPotencia,
)
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal


class SegmentadorRegimenesService:
    """Parte el eje de potencia en regímenes de operación (partición modal).

    El histograma de potencia de una máquina es multimodal: cada moda es una
    "potencia típica" (un régimen estable) y cada antimoda (valle) es la frontera
    entre dos regímenes. Este servicio estima la densidad, encuentra las modas que
    valen la pena y devuelve la partición sin requerir librerías externas.
    """

    MIN_LECTURAS = 20
    NUM_BINS_POR_DEFECTO = 60
    VENTANA_SUAVIZADO = 3

    PERSISTENCIA_MINIMA_RELATIVA = 0.25
    DECADAS_MAXIMAS = 5.0
    EPSILON_MINIMO_W = 0.01

    VENTANAS_BARRIDO = (1, 3, 5, 7, 9, 11, 13, 15)
    FRACCION_CONSISTENCIA_MINIMA = 0.6
    FACTOR_HUECO_CADENCIA = 3.0

    NUM_SUBVENTANAS_ESTACIONARIEDAD = 4
    DERIVA_MAXIMA_RELATIVA = 0.20

    # Delegados para mantener compatibilidad total con métodos estáticos/privados
    _percentil = staticmethod(percentil)
    _suavizar = staticmethod(suavizar)
    _detectar_picos_locales = staticmethod(detectar_picos_locales)
    _persistencia_de_modas = staticmethod(persistencia_de_modas)
    _seleccionar_modas = staticmethod(seleccionar_modas)
    _antimoda_entre = staticmethod(antimoda_entre)
    _barrer_ancho_banda = staticmethod(barrer_ancho_banda)
    _estimar_cadencia_nominal = staticmethod(estimar_cadencia_nominal)
    _deltas_potencia_validos = staticmethod(deltas_potencia_validos)
    _tasas_de_variacion = staticmethod(tasas_de_variacion)
    _clasificar_naturaleza = staticmethod(clasificar_naturaleza)

    @classmethod
    def _estimar_epsilon(cls, lecturas_w: list[float], piso_resolucion_w: float | None = None) -> float:
        return estimar_epsilon(lecturas_w, piso_resolucion_w, cls.DECADAS_MAXIMAS, cls.EPSILON_MINIMO_W)

    @classmethod
    def _construir_bins_log(cls, lecturas_w: list[float], num_bins: int, eps_w: float) -> tuple[list[float], list[int]]:
        return construir_bins_log(lecturas_w, num_bins, eps_w)

    @classmethod
    def _armar_regimenes(
        cls,
        lecturas_w: list[float],
        bordes: list[float],
        suavizados: list[float],
        modas: list[int],
        persistencias: dict[int, tuple[float, int | None]],
    ) -> list[RegimenOperacion]:
        if not modas:
            return []

        cortes_w = [
            (lambda j: (bordes[j] + bordes[j + 1]) / 2.0)(cls._antimoda_entre(suavizados, izq, der))
            for izq, der in itertools.pairwise(modas)
        ]

        grupos: list[list[float]] = [[] for _ in modas]
        for valor in lecturas_w:
            grupos[bisect.bisect_right(cortes_w, valor)].append(valor)

        total = len(lecturas_w)
        limites = [bordes[0], *cortes_w, bordes[-1]]
        regimenes: list[RegimenOperacion] = []

        for indice, (bin_moda, valores) in enumerate(zip(modas, grupos, strict=True)):
            mediana = statistics.median(valores) if valores else (bordes[bin_moda] + bordes[bin_moda + 1]) / 2.0
            mad = statistics.median([abs(v - mediana) for v in valores]) if valores else 0.0
            persistencia = persistencias.get(bin_moda, (0.0, None))[0]
            regimenes.append(
                RegimenOperacion(
                    indice=indice,
                    potencia_tipica_w=round((bordes[bin_moda] + bordes[bin_moda + 1]) / 2.0, 4),
                    limite_inferior_w=round(limites[indice], 4),
                    limite_superior_w=round(limites[indice + 1], 4),
                    masa=round(len(valores) / total, 6) if total else 0.0,
                    mediana_w=round(mediana, 4),
                    mad_w=round(mad, 4),
                    persistencia=round(persistencia / max(suavizados) if math.isfinite(persistencia) else 1.0, 4),
                )
            )
        return regimenes

    @classmethod
    def evaluar_estacionariedad(
        cls,
        lecturas: list[LecturaPotenciaTemporal],
        num_subventanas: int | None = None,
        num_bins: int | None = None,
    ) -> DiagnosticoEstacionariedad:
        return _evaluar_estacionariedad_fn(
            lecturas=lecturas,
            analizar_fn=cls.analizar,
            num_subventanas=num_subventanas,
            num_bins=num_bins,
            min_lecturas=cls.MIN_LECTURAS,
            num_subventanas_default=cls.NUM_SUBVENTANAS_ESTACIONARIEDAD,
            deriva_maxima_relativa=cls.DERIVA_MAXIMA_RELATIVA,
            epsilon_minimo_w=cls.EPSILON_MINIMO_W,
        )

    @classmethod
    def analizar(
        cls,
        lecturas_w: list[float],
        num_bins: int | None = None,
        piso_resolucion_w: float | None = None,
        persistencia_minima_relativa: float | None = None,
        con_barrido: bool = True,
    ) -> SegmentacionPotencia:
        """Segmenta la distribución de potencia en regímenes. Punto de entrada del servicio."""
        bins = num_bins or cls.NUM_BINS_POR_DEFECTO
        persistencia = (
            persistencia_minima_relativa
            if persistencia_minima_relativa is not None
            else cls.PERSISTENCIA_MINIMA_RELATIVA
        )
        no_positivas = sum(1 for v in lecturas_w if v <= 0.0)

        if len(lecturas_w) < cls.MIN_LECTURAS:
            return SegmentacionPotencia([], [], [], 0.0, len(lecturas_w), no_positivas)

        eps = cls._estimar_epsilon(lecturas_w, piso_resolucion_w)
        bordes, conteos = cls._construir_bins_log(lecturas_w, bins, eps)
        suavizados = cls._suavizar(conteos, cls.VENTANA_SUAVIZADO)

        modas = cls._seleccionar_modas(suavizados, persistencia)
        persistencias = cls._persistencia_de_modas(suavizados)
        regimenes = cls._armar_regimenes(lecturas_w, bordes, suavizados, modas, persistencias)

        return SegmentacionPotencia(
            bordes_bins_w=[round(b, 4) for b in bordes],
            frecuencias=conteos,
            regimenes=regimenes,
            epsilon_w=round(eps, 6),
            lecturas_analizadas=len(lecturas_w),
            lecturas_no_positivas=no_positivas,
            diagnostico_modal=cls._barrer_ancho_banda(conteos, persistencia) if con_barrido else None,
        )

    @classmethod
    def analizar_serie(
        cls,
        lecturas: list[LecturaPotenciaTemporal],
        num_bins: int | None = None,
        piso_resolucion_w: float | None = None,
        persistencia_minima_relativa: float | None = None,
    ) -> SegmentacionPotencia:
        """`analizar` más lo que solo la serie temporal puede aportar: dinámica y deriva."""
        potencias = [lectura.potencia_w for lectura in lecturas]
        base = cls.analizar(potencias, num_bins, piso_resolucion_w, persistencia_minima_relativa)
        cadencia = cls._estimar_cadencia_nominal(lecturas)

        regimenes = base.regimenes
        if cadencia:
            regimenes = cls._clasificar_naturaleza(regimenes, cls._tasas_de_variacion(lecturas, cadencia), cadencia)

        return SegmentacionPotencia(
            bordes_bins_w=base.bordes_bins_w,
            frecuencias=base.frecuencias,
            regimenes=regimenes,
            epsilon_w=base.epsilon_w,
            lecturas_analizadas=base.lecturas_analizadas,
            lecturas_no_positivas=base.lecturas_no_positivas,
            diagnostico_modal=base.diagnostico_modal,
            diagnostico_estacionariedad=cls.evaluar_estacionariedad(lecturas, num_bins=num_bins),
            cadencia_mediana_s=cadencia,
        )

    @classmethod
    def segmentar(
        cls,
        lecturas_w: list[float],
        num_bins: int | None = None,
        piso_resolucion_w: float | None = None,
        persistencia_minima_relativa: float | None = None,
        con_barrido: bool = True,
    ) -> list[RegimenOperacion]:
        return cls.analizar(
            lecturas_w,
            num_bins=num_bins,
            piso_resolucion_w=piso_resolucion_w,
            persistencia_minima_relativa=persistencia_minima_relativa,
            con_barrido=con_barrido,
        ).regimenes

    @classmethod
    def segmentar_con_transiciones(
        cls,
        lecturas: list[LecturaPotenciaTemporal],
        num_bins: int | None = None,
        piso_resolucion_w: float | None = None,
        persistencia_minima_relativa: float | None = None,
    ) -> list[RegimenOperacion]:
        return cls.analizar_serie(
            lecturas,
            num_bins=num_bins,
            piso_resolucion_w=piso_resolucion_w,
            persistencia_minima_relativa=persistencia_minima_relativa,
        ).regimenes

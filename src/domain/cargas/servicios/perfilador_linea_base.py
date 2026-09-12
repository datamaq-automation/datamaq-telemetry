"""src/domain/cargas/servicios/perfilador_linea_base.py — Línea de base de un medidor agregado: cuánto se consume cuando nadie hace nada."""

from collections import defaultdict
from datetime import tzinfo

from src.domain.cargas.servicios.estadistica import (
    cadencia_mediana_segundos,
    mediana,
    percentil,
)
from src.domain.cargas.value_objects import PerfilLineaBase
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal


def _redondear(valor: float | None) -> float | None:
    return round(valor, 2) if valor is not None else None


class PerfiladorLineaBaseService:
    """Separa el consumo permanente del consumo de actividad.

    Es el único análisis de desagregación que da un resultado sólido a cadencia de
    5 minutos, y no necesita ninguna firma calibrada: se apoya en que hay franjas
    horarias en las que, por conducta y no por estadística, solo quedan encendidas las
    cargas autónomas (refrigeración, standby).

    El estimador de cada ventana es un **percentil bajo, no el mínimo**: el mínimo es
    una sola muestra y cualquier lectura espuria lo fija; el percentil 10 sobre una
    ventana de una hora sobrevive a un outlier sin dejar de estar "abajo".
    """

    MIN_LECTURAS = 20
    VENTANA_SEGUNDOS = 3600.0
    PERCENTIL_BASE = 0.10
    MIN_MUESTRAS_VENTANA = 3

    HORAS_NOCTURNAS = (2, 3, 4)
    """Franja en la que se asume que no hay actividad humana. Ni la 0 ni la 1, que
    todavía atrapan cocina y lavado tardíos; ni la 5, que ya atrapa termotanques
    programados para la mañana."""

    HORAS_DIURNAS = tuple(range(10, 23))

    @classmethod
    def _bases_por_ventana(cls, lecturas: list[LecturaPotenciaTemporal], zona: tzinfo | None) -> dict[int, list[float]]:
        """Percentil bajo de cada ventana horaria, agrupado por hora local del día.

        La clave es la hora local (0-23) y no la ventana absoluta: lo que interesa es
        comparar franjas entre sí, promediando todos los días de la muestra.
        """
        por_ventana: dict[tuple[int, int], list[float]] = defaultdict(list)
        for lectura in lecturas:
            momento = lectura.momento.astimezone(zona) if zona is not None else lectura.momento
            ventana = int(lectura.momento.timestamp() // cls.VENTANA_SEGUNDOS)
            por_ventana[(momento.hour, ventana)].append(lectura.potencia_w)

        por_hora: dict[int, list[float]] = defaultdict(list)
        for (hora, _), potencias in por_ventana.items():
            if len(potencias) < cls.MIN_MUESTRAS_VENTANA:
                continue
            base = percentil(potencias, cls.PERCENTIL_BASE)
            if base is not None:
                por_hora[hora].append(base)
        return por_hora

    @classmethod
    def _base_de_franja(cls, por_hora: dict[int, list[float]], horas: tuple[int, ...]) -> tuple[float | None, int]:
        bases = [b for hora in horas for b in por_hora.get(hora, [])]
        return mediana(bases), len(bases)

    @classmethod
    def perfilar(
        cls,
        lecturas: list[LecturaPotenciaTemporal],
        zona: tzinfo | None = None,
    ) -> PerfilLineaBase:
        """Punto de entrada del servicio. Devuelve un perfil vacío si no hay datos suficientes."""
        potencias = [lectura.potencia_w for lectura in lecturas]
        potencia_media = _redondear(mediana(potencias))
        potencia_maxima = _redondear(max(potencias) if potencias else None)

        if len(lecturas) < cls.MIN_LECTURAS:
            return PerfilLineaBase(
                linea_base_w=None,
                linea_base_nocturna_w=None,
                linea_base_diurna_w=None,
                delta_diurno_w=None,
                potencia_media_w=potencia_media,
                potencia_maxima_w=potencia_maxima,
                muestras=len(lecturas),
                ventanas_nocturnas=0,
                ventanas_diurnas=0,
            )

        por_hora = cls._bases_por_ventana(lecturas, zona)
        nocturna, ventanas_nocturnas = cls._base_de_franja(por_hora, cls.HORAS_NOCTURNAS)
        diurna, ventanas_diurnas = cls._base_de_franja(por_hora, cls.HORAS_DIURNAS)
        todas = [b for bases in por_hora.values() for b in bases]

        delta = None
        if nocturna is not None and diurna is not None:
            delta = round(diurna - nocturna, 2)

        return PerfilLineaBase(
            linea_base_w=_redondear(mediana(todas)),
            linea_base_nocturna_w=_redondear(nocturna),
            linea_base_diurna_w=_redondear(diurna),
            delta_diurno_w=delta,
            potencia_media_w=potencia_media,
            potencia_maxima_w=potencia_maxima,
            muestras=len(lecturas),
            ventanas_nocturnas=ventanas_nocturnas,
            ventanas_diurnas=ventanas_diurnas,
            cadencia_mediana_s=cadencia_mediana_segundos([lectura.momento for lectura in lecturas]),
        )

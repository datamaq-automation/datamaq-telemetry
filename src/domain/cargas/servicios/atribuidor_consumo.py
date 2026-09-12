"""src/domain/cargas/servicios/atribuidor_consumo.py — Reparto del consumo de un período entre las cargas conocidas, con residual explícito."""

from collections import defaultdict
from datetime import datetime

from src.domain.cargas.entities import Carga, IntervaloActividadCarga
from src.domain.cargas.value_objects import AtribucionConsumo, ItemAtribucion

NO_ATRIBUIDO = "No atribuido"

_SIN_TOTAL = (
    "No hay lecturas del contador acumulado en el período, así que no se puede cerrar el balance "
    "contra el consumo real: los porcentajes son sobre lo atribuido, no sobre el total."
)
_RESIDUAL_ALTO = (
    "Queda sin atribuir el {pct:.0%} del consumo. A cadencia de 5 minutos es lo esperado — las "
    "cargas breves y la iluminación no se detectan como eventos —, pero también puede indicar "
    "cargas del catálogo sin firma calibrada."
)
_RESIDUAL_NEGATIVO = (
    "Lo atribuido ({atribuido:.2f} kWh) supera al consumo real medido por el contador "
    "({total:.2f} kWh). Hay cargas contándose dos veces: revisá firmas con potencias solapadas."
)


class AtribuidorConsumoService:
    """Convierte intervalos de actividad en un reparto de kWh, y dice cuánto no explica.

    El total del período **sale del contador acumulado**, no de integrar la serie
    instantánea. Entre dos muestras de 5 minutos puede haber prendido y apagado
    cualquier cosa; esa integral sería sistemáticamente sesgada, mientras que el
    contador es exacto por construcción.

    El residual no se fuerza a cero. Si lo atribuido supera al total, el servicio lo
    dice en vez de repartir la diferencia: un balance que siempre cierra no informa nada.
    """

    RESIDUAL_MAXIMO_ACEPTABLE = 0.40

    @staticmethod
    def _energia_de(intervalo: IntervaloActividadCarga) -> float:
        if intervalo.energia_kwh is not None:
            return intervalo.energia_kwh
        if intervalo.potencia_media_w is None:
            return 0.0
        return intervalo.potencia_media_w * intervalo.duracion_segundos / 3_600_000.0

    @classmethod
    def _agrupar(
        cls,
        intervalos: list[IntervaloActividadCarga],
        nombres: dict[str, str],
        residual_kwh: float,
        denominador_kwh: float,
    ) -> tuple[list[ItemAtribucion], float]:
        """Un item por carga, más **uno solo** para todo lo que no se atribuyó.

        El residual del balance y los intervalos detectados pero no imputados son la
        misma cosa desde el punto de vista de quien lee el reporte —consumo que el motor
        no puede explicar— y por eso van juntos. Separarlos daba dos filas homónimas.

        Los porcentajes se calculan todos contra el mismo denominador: el consumo real
        del contador cuando está disponible. Con denominadores distintos por item la
        suma se pasaba del 100% y el reporte dejaba de ser interpretable.
        """
        energias: dict[str | None, float] = defaultdict(float)
        conteos: dict[str | None, int] = defaultdict(int)
        confianzas: dict[str | None, list[float]] = defaultdict(list)

        for intervalo in intervalos:
            clave = intervalo.carga_id
            energias[clave] += cls._energia_de(intervalo)
            conteos[clave] += 1
            if intervalo.confianza is not None:
                confianzas[clave].append(intervalo.confianza)

        atribuida = sum(energias.values())
        if residual_kwh > 0:
            energias[None] += residual_kwh
            conteos.setdefault(None, 0)

        base = denominador_kwh if denominador_kwh > 0 else atribuida
        items = [
            ItemAtribucion(
                carga_id=clave,
                nombre=nombres.get(clave, NO_ATRIBUIDO) if clave else NO_ATRIBUIDO,
                energia_kwh=round(energia, 4),
                porcentaje=round(energia / base, 4) if base > 0 else 0.0,
                intervalos=conteos[clave],
                confianza_media=(
                    round(sum(confianzas[clave]) / len(confianzas[clave]), 4) if confianzas[clave] else None
                ),
            )
            for clave, energia in energias.items()
        ]
        return sorted(items, key=lambda i: i.energia_kwh, reverse=True), atribuida

    @classmethod
    def atribuir(
        cls,
        desde: datetime,
        hasta: datetime,
        intervalos: list[IntervaloActividadCarga],
        cargas: list[Carga],
        energia_total_kwh: float | None,
    ) -> AtribucionConsumo:
        """Punto de entrada del servicio."""
        nombres = {c.id: c.nombre for c in cargas}

        if energia_total_kwh is None or energia_total_kwh <= 0:
            items, atribuida = cls._agrupar(intervalos, nombres, residual_kwh=0.0, denominador_kwh=0.0)
            return AtribucionConsumo(
                desde=desde,
                hasta=hasta,
                energia_total_kwh=energia_total_kwh,
                energia_atribuida_kwh=round(atribuida, 4),
                residual_kwh=None,
                residual_porcentaje=None,
                items=items,
                calidad_suficiente=False,
                advertencia=_SIN_TOTAL,
            )

        # Se agrupa una vez sin residual para conocer lo atribuido, y otra ya con él:
        # el residual depende del total atribuido, y el total atribuido no depende del
        # residual, así que el orden queda determinado.
        _, atribuida = cls._agrupar(intervalos, nombres, residual_kwh=0.0, denominador_kwh=energia_total_kwh)
        residual = energia_total_kwh - atribuida
        fraccion = residual / energia_total_kwh
        items, _ = cls._agrupar(intervalos, nombres, max(residual, 0.0), energia_total_kwh)

        advertencia = None
        if residual < 0:
            advertencia = _RESIDUAL_NEGATIVO.format(atribuido=atribuida, total=energia_total_kwh)
        elif fraccion > cls.RESIDUAL_MAXIMO_ACEPTABLE:
            advertencia = _RESIDUAL_ALTO.format(pct=fraccion)

        return AtribucionConsumo(
            desde=desde,
            hasta=hasta,
            energia_total_kwh=round(energia_total_kwh, 4),
            energia_atribuida_kwh=round(atribuida, 4),
            residual_kwh=round(residual, 4),
            residual_porcentaje=round(fraccion, 4),
            items=items,
            calidad_suficiente=0 <= fraccion <= cls.RESIDUAL_MAXIMO_ACEPTABLE,
            advertencia=advertencia,
        )

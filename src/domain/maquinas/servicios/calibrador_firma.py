"""src/domain/maquinas/servicios/calibrador_firma.py — Cálculo de la firma de una carga a partir de las muestras de una campaña."""

import itertools
import math

from src.domain.maquinas.servicios.analizador_ciclos import AnalizadorCiclosService
from src.domain.maquinas.servicios.estadistica import (
    cadencia_mediana_segundos,
    desviacion_absoluta_mediana,
    mediana,
    percentil,
)
from src.domain.maquinas.value_objects import (
    EstadoCampana,
    FirmaCarga,
    MotivoDescarte,
    MuestraCampana,
    OrigenFirma,
    ResultadoCalibracion,
    TipoCampana,
)
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal


class CalibradorFirmaService:
    """Convierte una campaña en una firma medida, o explica por qué no pudo.

    Toda la medición es **diferencial contra la línea de base**: lo que se quiere
    caracterizar no es lo que marca el medidor, sino lo que la carga *agrega* a lo que
    la casa ya consumía. Sin esa resta, la firma de una pava incluiría a la heladera.

    El servicio prefiere devolver `CONTAMINADA` antes que una firma dudosa. Una firma
    es un dato que después se usa a ciegas durante meses para atribuir consumo; una
    campaña que hay que repetir cuesta diez minutos.
    """

    MIN_MUESTRAS = 10
    PRE_ROLL_SEGUNDOS = 60.0
    """Ventana inicial reservada para medir la línea de base: el operador arranca la
    campaña, espera, y recién entonces prende el aparato."""

    TRANSITORIO_SEGUNDOS = 5.0
    """Se excluye del régimen pero se conserva como `pico_arranque_w`: el pico de un
    motor es 6-8 veces su nominal y contaminaría la mediana de régimen."""

    MARGEN_ENCENDIDO_W = 50.0
    """Cuánto tiene que superar a la línea de base para contar como encendido."""

    FRACCION_CONTAMINACION = 0.25
    ESCALON_AJENO_W = 100.0
    MIN_CICLOS_PASIVA = 3
    PERCENTIL_LINEA_BASE_PASIVA = 0.10
    FACTOR_UMBRAL_PASIVA = 1.15

    @classmethod
    def _sin_firma(
        cls,
        motivo: MotivoDescarte,
        muestras: int,
        detalle: str | None = None,
        linea_base_w: float | None = None,
    ) -> ResultadoCalibracion:
        """Resultado sin firma. `firma` queda en `None` por construcción, no por olvido."""
        return ResultadoCalibracion(
            estado=EstadoCampana.CONTAMINADA,
            motivo=motivo,
            muestras_analizadas=muestras,
            detalle=detalle,
            linea_base_w=round(linea_base_w, 2) if linea_base_w is not None else None,
        )

    @staticmethod
    def _factor_potencia(potencia_w: float, reactiva_var: float | None) -> float | None:
        if reactiva_var is None:
            return None
        aparente = math.hypot(potencia_w, reactiva_var)
        if aparente <= 0:
            return None
        return round(potencia_w / aparente, 3)

    @classmethod
    def _linea_base_activa(cls, muestras: list[MuestraCampana]) -> tuple[float | None, float | None]:
        """Mediana del pre-roll: lo que la casa consumía antes de prender el aparato."""
        inicio = muestras[0].momento
        preroll = [m for m in muestras if (m.momento - inicio).total_seconds() < cls.PRE_ROLL_SEGUNDOS]
        if not preroll:
            return None, None
        reactivas = [m.potencia_reactiva_var for m in preroll if m.potencia_reactiva_var is not None]
        return mediana([m.potencia_w for m in preroll]), mediana(reactivas)

    @classmethod
    def _tramo_encendido(cls, muestras: list[MuestraCampana], linea_base_w: float) -> list[MuestraCampana]:
        """Muestras por encima del umbral, desde el primer encendido hasta el último."""
        umbral = linea_base_w + cls.MARGEN_ENCENDIDO_W
        indices = [i for i, m in enumerate(muestras) if m.potencia_w >= umbral]
        return muestras[indices[0] : indices[-1] + 1] if indices else []

    @classmethod
    def _escalon_ajeno(cls, regimen: list[MuestraCampana]) -> float | None:
        """Mayor salto dentro del régimen. Un escalón grande acá es otra carga entrando."""
        saltos = [abs(b.potencia_w - a.potencia_w) for a, b in itertools.pairwise(regimen)]
        maximo = max(saltos) if saltos else 0.0
        return maximo if maximo > cls.ESCALON_AJENO_W else None

    @classmethod
    def _diagnosticar_contaminacion(
        cls,
        regimen: list[MuestraCampana],
        dispersion_relativa: float,
        base_w: float,
        total_muestras: int,
    ) -> ResultadoCalibracion | None:
        """Detecta que durante la ventana entró algo que no es la carga que se medía.

        Dos síntomas independientes: la potencia se movió demasiado en régimen, o hubo
        un escalón neto en el medio. El segundo atrapa el caso que el primero no ve —
        una carga que entra y se queda desplaza la mediana sin dispersarla mucho.
        """
        if dispersion_relativa > cls.FRACCION_CONTAMINACION:
            return cls._sin_firma(
                MotivoDescarte.DISPERSION_EXCESIVA,
                total_muestras,
                detalle=f"La potencia varió un {dispersion_relativa:.0%} durante la medición, por encima "
                f"del {cls.FRACCION_CONTAMINACION:.0%} tolerado. Probablemente se prendió algo más.",
                linea_base_w=base_w,
            )

        ajeno = cls._escalon_ajeno(regimen)
        if ajeno is not None:
            return cls._sin_firma(
                MotivoDescarte.ESCALON_AJENO,
                total_muestras,
                detalle=f"Apareció un escalón de {ajeno:.0f} W dentro de la ventana: otra carga entró "
                "en medio de la medición.",
                linea_base_w=base_w,
            )
        return None

    @classmethod
    def _calibrar_activa(cls, muestras: list[MuestraCampana]) -> ResultadoCalibracion:
        base_w, base_var = cls._linea_base_activa(muestras)
        if base_w is None:
            return cls._sin_firma(MotivoDescarte.SIN_LINEA_BASE, len(muestras))

        tramo = cls._tramo_encendido(muestras, base_w)
        if len(tramo) < 2:
            return cls._sin_firma(
                MotivoDescarte.SIN_ENCENDIDO_DETECTADO,
                len(muestras),
                detalle=f"Ninguna muestra superó la línea de base ({base_w:.1f} W) por más de "
                f"{cls.MARGEN_ENCENDIDO_W:.0f} W. ¿Se prendió el aparato durante la ventana?",
                linea_base_w=base_w,
            )

        # El corte se hace por índice y no por pertenencia: el tramo puede repetir
        # valores idénticos y compararlos por igualdad los confundiría entre sí.
        arranque = tramo[0].momento
        corte = next(
            (i for i, m in enumerate(tramo) if (m.momento - arranque).total_seconds() >= cls.TRANSITORIO_SEGUNDOS),
            0,
        )
        transitorio, regimen = (tramo[:corte], tramo[corte:]) if tramo[corte:] else ([], tramo)

        potencias = [m.potencia_w - base_w for m in regimen]
        centro = mediana(potencias)
        dispersion = desviacion_absoluta_mediana(potencias) or 0.0
        if centro is None or centro <= 0:
            return cls._sin_firma(MotivoDescarte.SIN_ENCENDIDO_DETECTADO, len(muestras), linea_base_w=base_w)

        relativa = round(dispersion / centro, 4)
        contaminacion = cls._diagnosticar_contaminacion(regimen, relativa, base_w, len(muestras))
        if contaminacion is not None:
            return contaminacion

        cadencia = cadencia_mediana_segundos([m.momento for m in muestras])
        reactivas = [
            m.potencia_reactiva_var - (base_var or 0.0) for m in regimen if m.potencia_reactiva_var is not None
        ]
        reactiva = mediana(reactivas)
        pico = max((m.potencia_w - base_w for m in transitorio), default=None)
        duracion = (tramo[-1].momento - tramo[0].momento).total_seconds() + (cadencia or 0.0)

        return ResultadoCalibracion(
            estado=EstadoCampana.COMPLETADA,
            firma=FirmaCarga(
                potencia_w=round(centro, 2),
                dispersion_w=round(dispersion, 2),
                potencia_reactiva_var=round(reactiva, 2) if reactiva is not None else None,
                factor_potencia=cls._factor_potencia(centro, reactiva),
                duracion_encendido_s=round(duracion, 1),
                pico_arranque_w=round(pico, 2) if pico is not None else None,
                origen=OrigenFirma.CAMPANA,
                muestras=len(regimen),
                medida_en=muestras[-1].momento,
            ),
            linea_base_w=round(base_w, 2),
            linea_base_var=round(base_var, 2) if base_var is not None else None,
            muestras_analizadas=len(muestras),
            muestras_en_regimen=len(regimen),
            dispersion_relativa=relativa,
            cadencia_mediana_s=cadencia,
        )

    @classmethod
    def _calibrar_pasiva(cls, muestras: list[MuestraCampana]) -> ResultadoCalibracion:
        """La carga cicla sola: la línea de base es su propio reposo y hay que ver varios ciclos."""
        potencias = [m.potencia_w for m in muestras]
        base_w = percentil(potencias, cls.PERCENTIL_LINEA_BASE_PASIVA)
        if base_w is None:
            return cls._sin_firma(MotivoDescarte.SIN_LINEA_BASE, len(muestras))

        serie = [LecturaPotenciaTemporal(momento=m.momento, potencia_w=m.potencia_w) for m in muestras]
        umbral = max(base_w * cls.FACTOR_UMBRAL_PASIVA, base_w + cls.MARGEN_ENCENDIDO_W)
        estadistica = AnalizadorCiclosService.analizar(serie, umbral_encendido_w=umbral)

        if estadistica.ciclos < cls.MIN_CICLOS_PASIVA:
            return cls._sin_firma(
                MotivoDescarte.CICLOS_INSUFICIENTES,
                len(muestras),
                detalle=f"Se observaron {estadistica.ciclos} ciclos; hacen falta al menos "
                f"{cls.MIN_CICLOS_PASIVA} para hablar de un período típico. La ventana fue corta.",
                linea_base_w=round(base_w, 2),
            )

        encendidas = [m for m in muestras if m.potencia_w >= umbral]
        potencias_carga = [m.potencia_w - base_w for m in encendidas]
        centro = mediana(potencias_carga)
        if centro is None or centro <= 0:
            return cls._sin_firma(MotivoDescarte.SIN_ENCENDIDO_DETECTADO, len(muestras), linea_base_w=base_w)

        dispersion = desviacion_absoluta_mediana(potencias_carga) or 0.0
        reactivas = [m.potencia_reactiva_var for m in encendidas if m.potencia_reactiva_var is not None]
        reactiva = mediana(reactivas)

        return ResultadoCalibracion(
            estado=EstadoCampana.COMPLETADA,
            firma=FirmaCarga(
                potencia_w=round(centro, 2),
                dispersion_w=round(dispersion, 2),
                potencia_reactiva_var=round(reactiva, 2) if reactiva is not None else None,
                factor_potencia=cls._factor_potencia(centro, reactiva),
                duracion_encendido_s=estadistica.duracion_encendido_mediana_s,
                duracion_encendido_mad_s=estadistica.duracion_encendido_mad_s,
                duracion_apagado_s=estadistica.duracion_apagado_mediana_s,
                origen=OrigenFirma.CAMPANA,
                muestras=len(encendidas),
                medida_en=muestras[-1].momento,
            ),
            linea_base_w=round(base_w, 2),
            muestras_analizadas=len(muestras),
            muestras_en_regimen=len(encendidas),
            dispersion_relativa=round(dispersion / centro, 4),
            cadencia_mediana_s=estadistica.cadencia_mediana_s,
        )

    @classmethod
    def calibrar(cls, muestras: list[MuestraCampana], tipo: TipoCampana) -> ResultadoCalibracion:
        """Punto de entrada del servicio."""
        if len(muestras) < cls.MIN_MUESTRAS:
            return cls._sin_firma(
                MotivoDescarte.SIN_MUESTRAS,
                len(muestras),
                detalle=f"Solo llegaron {len(muestras)} muestras. ¿El medidor entró en modo ráfaga?",
            )
        ordenadas = sorted(muestras, key=lambda m: m.momento)
        if tipo == TipoCampana.PASIVA:
            return cls._calibrar_pasiva(ordenadas)
        return cls._calibrar_activa(ordenadas)

"""src/application/use_cases/analizar_consumo.py."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.application.dtos.carga_dto import (
    EstadisticaCiclosDTO,
    PerfilConsumoResponseDTO,
    PerfilLineaBaseDTO,
)
from src.application.dtos.maquina_dto import RegimenOperacionDTO
from src.domain.cargas.ports import RepositorioSeriePotenciaPort
from src.domain.cargas.servicios.analizador_ciclos import AnalizadorCiclosService
from src.domain.cargas.servicios.perfilador_linea_base import PerfiladorLineaBaseService
from src.domain.cargas.value_objects import EstadisticaCiclos, PerfilLineaBase
from src.domain.disponibilidad.services import SegmentadorRegimenesService
from src.domain.telemetria.exceptions import ZonaHorariaInvalidaError
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal

ZONA_POR_DEFECTO = "America/Argentina/Buenos_Aires"

_ADVERTENCIA_CADENCIA = (
    "A una cadencia de {cadencia:.0f} s, un encendido más corto que ~{minimo:.0f} s no puede "
    "detectarse como evento propio: el medidor nunca lo muestreó. Las cargas breves "
    "(pava, hornalla puntual) y la iluminación no aparecen acá y quedan dentro de la "
    "línea de base o sin atribuir."
)


class AnalizarConsumoUseCase:
    """Análisis batch de la serie agregada de un medidor.

    Deliberadamente diferido y no en la ingesta: la duración de un encendido es parte
    de lo que lo identifica, y en vivo no se conoce hasta que el evento terminó. Correr
    esto sobre una ventana cerrada permite además reprocesar cuando se corrige una
    etiqueta, sin meter trabajo pesado en el camino crítico de MQTT.
    """

    LIMITE_LECTURAS = 200_000
    FACTOR_MARGEN_LINEA_BASE = 1.15
    """El umbral de ciclado se pone un 15% por encima de la línea de base: pegado a ella,
    el ruido propio del fondo generaría encendidos fantasma."""

    MULTIPLO_MINIMO_DETECTABLE = 2.0

    def __init__(self, repo_serie: RepositorioSeriePotenciaPort):
        self.repo_serie = repo_serie

    @staticmethod
    def _resolver_zona(zona: str) -> ZoneInfo:
        try:
            return ZoneInfo(zona)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ZonaHorariaInvalidaError(f"Zona horaria inválida: {zona}") from exc

    @staticmethod
    def _linea_base_a_dto(perfil: PerfilLineaBase) -> PerfilLineaBaseDTO:
        return PerfilLineaBaseDTO(
            linea_base_W=perfil.linea_base_w,
            linea_base_nocturna_W=perfil.linea_base_nocturna_w,
            linea_base_diurna_W=perfil.linea_base_diurna_w,
            delta_diurno_W=perfil.delta_diurno_w,
            potencia_media_W=perfil.potencia_media_w,
            potencia_maxima_W=perfil.potencia_maxima_w,
            muestras=perfil.muestras,
            ventanas_nocturnas=perfil.ventanas_nocturnas,
            ventanas_diurnas=perfil.ventanas_diurnas,
            cadencia_mediana_s=perfil.cadencia_mediana_s,
        )

    @staticmethod
    def _ciclos_a_dto(estadistica: EstadisticaCiclos) -> EstadisticaCiclosDTO:
        return EstadisticaCiclosDTO(
            ciclos=estadistica.ciclos,
            duracion_encendido_mediana_s=estadistica.duracion_encendido_mediana_s,
            duracion_encendido_mad_s=estadistica.duracion_encendido_mad_s,
            duracion_apagado_mediana_s=estadistica.duracion_apagado_mediana_s,
            duracion_apagado_mad_s=estadistica.duracion_apagado_mad_s,
            periodo_mediano_s=estadistica.periodo_mediano_s,
            duty_cycle=estadistica.duty_cycle,
            patron=estadistica.patron,
            es_regular=estadistica.es_regular,
            cadencia_mediana_s=estadistica.cadencia_mediana_s,
        )

    @classmethod
    def _advertencia(cls, cadencia: float | None) -> str | None:
        if cadencia is None:
            return None
        return _ADVERTENCIA_CADENCIA.format(cadencia=cadencia, minimo=cadencia * cls.MULTIPLO_MINIMO_DETECTABLE)

    def _umbral_ciclos(self, perfil: PerfilLineaBase) -> float | None:
        base = perfil.linea_base_nocturna_w if perfil.linea_base_nocturna_w is not None else perfil.linea_base_w
        if base is None or base <= 0:
            return None
        return round(base * self.FACTOR_MARGEN_LINEA_BASE, 2)

    def _regimenes(self, lecturas: list[LecturaPotenciaTemporal]) -> list[RegimenOperacionDTO]:
        """Partición modal de la potencia, reusando el motor ya en producción."""
        segmentacion = SegmentadorRegimenesService.analizar_serie(lecturas)
        return [
            RegimenOperacionDTO(
                indice=r.indice,
                potencia_tipica_w=r.potencia_tipica_w,
                limite_inferior_w=r.limite_inferior_w,
                limite_superior_w=r.limite_superior_w,
                masa=r.masa,
                mediana_w=r.mediana_w,
                mad_w=r.mad_w,
                persistencia=r.persistencia,
                variacion_mediana_w_s=r.variacion_mediana_w_s,
                naturaleza=r.naturaleza,
            )
            for r in segmentacion.regimenes
        ]

    def perfilar(
        self,
        dispositivo_id: str,
        dias: int = 14,
        zona: str = ZONA_POR_DEFECTO,
        limite: int | None = None,
    ) -> PerfilConsumoResponseDTO:
        """Qué se puede afirmar del medidor sin ninguna firma calibrada todavía."""
        zona_info = self._resolver_zona(zona)
        limite_efectivo = limite if limite is not None else self.LIMITE_LECTURAS
        hasta = datetime.now(timezone.utc)
        desde = hasta - timedelta(days=dias)

        lecturas = self.repo_serie.listar_serie_potencia(dispositivo_id, desde, hasta, limite=limite_efectivo)
        perfil = PerfiladorLineaBaseService.perfilar(lecturas, zona=zona_info)

        umbral = self._umbral_ciclos(perfil)
        ciclos = (
            AnalizadorCiclosService.analizar(lecturas, umbral_encendido_w=umbral)
            if umbral is not None
            else AnalizadorCiclosService.analizar([], umbral_encendido_w=0.0)
        )

        return PerfilConsumoResponseDTO(
            dispositivo_id=dispositivo_id,
            desde=desde,
            hasta=hasta,
            dias_analizados=dias,
            zona_horaria=zona,
            cantidad_lecturas=len(lecturas),
            lecturas_truncadas=len(lecturas) >= limite_efectivo,
            linea_base=self._linea_base_a_dto(perfil),
            ciclos_sobre_linea_base=self._ciclos_a_dto(ciclos),
            umbral_ciclos_W=umbral,
            regimenes=self._regimenes(lecturas),
            advertencia_cadencia=self._advertencia(perfil.cadencia_mediana_s),
        )

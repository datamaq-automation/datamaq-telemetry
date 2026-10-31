"""src/domain/telemetria/servicios/calculos_potencia.py."""

import threading
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.domain.telemetria.entities import AcumuladoEnergia, EnergiaAgregada
from src.domain.telemetria.value_objects import GranularidadEnergia


class CalculadoraPotenciaService:
    """Cálculo canónico de potencia aparente y factor de potencia.

    El firmware Powermeter publica el formato compacto `{"n":"R","v":..,"i":..,"p":..,"q":..}`,
    sin potencia aparente. Antes nadie la derivaba en la ingesta y la agregación la
    aproximaba con `hypot(P, Q)`, así que una consulta `raw` devolvía `null` donde la
    agregada devolvía un número, y con dos definiciones distintas.

    Se unifica en `S = V_rms · I_rms`, que es la definición exacta de potencia aparente.
    A diferencia de `hypot(P, Q)`, incluye la potencia de distorsión, que en cargas
    conmutadas es sustancial: para una fase con V=227.7, I=0.9, P=147 y Q=-51, `hypot`
    da FP 0.94 mientras que V·I da 0.72. La diferencia es real y estaba invisible.
    """

    @staticmethod
    def calcular_potencia_aparente(tension_v: float | None, corriente_a: float | None) -> float | None:
        """S = |V| · |I| en VA. `None` si falta cualquiera de los dos factores.

        Cero es un resultado válido —significa que no hay carga—, no un dato ausente.
        """
        if tension_v is None or corriente_a is None:
            return None
        return round(abs(tension_v) * abs(corriente_a), 2)

    @staticmethod
    def calcular_factor_potencia(
        potencia_activa_w: float | None,
        potencia_aparente_va: float | None,
    ) -> float | None:
        """FP = P / S, acotado a [-1, 1]. `None` si falta un término o si S <= 0.

        Sin potencia aparente el factor de potencia es indefinido, no óptimo: devolver
        1.0 sería la misma mentira optimista que arrastraba `determinar_estado_fp`.

        El acotado no es cosmético. `FactorPotencia` rechaza valores fuera de [-1, 1],
        y `S = V·I` se calcula con tensión y corriente redondeadas a dos decimales por
        el firmware, mientras que P se mide aparte: el cociente puede superar 1 por
        redondeo y hacer fallar la ingesta entera.

        Se preserva el signo de P, que distingue consumo de exportación (o un TI invertido).
        """
        if potencia_activa_w is None or potencia_aparente_va is None:
            return None
        if potencia_aparente_va <= 0.0:
            return None
        fp = potencia_activa_w / potencia_aparente_va
        return round(max(-1.0, min(1.0, fp)), 2)

    @staticmethod
    def calcular_potencia_aparente_total(*aparentes: float | None) -> float | None:
        """Potencia aparente aritmética trifásica: suma de las S de fase presentes."""
        presentes = [s for s in aparentes if s is not None]
        if not presentes:
            return None
        return round(sum(presentes), 2)


class AgregacionEnergiaService:
    """Agrega el contador acumulado de energía en consumos por periodo (día o mes).

    El consumo de un periodo es el delta del último acumulado respecto del último
    del periodo anterior, en la zona horaria configurada. El primer periodo no
    tiene referencia y se devuelve con ``energia_activa_neta_kwh=None``.
    """

    @staticmethod
    def _normalizar_utc(registrado_en: datetime) -> datetime:
        if registrado_en.tzinfo is None:
            return registrado_en.replace(tzinfo=timezone.utc)
        return registrado_en.astimezone(timezone.utc)

    @staticmethod
    def agregar_por_periodo(
        acumulados: list[AcumuladoEnergia],
        granularidad: GranularidadEnergia,
        zona: ZoneInfo,
    ) -> list[EnergiaAgregada]:
        ordenados = sorted(
            (a for a in acumulados if a.energia_activa_neta is not None),
            key=lambda a: AgregacionEnergiaService._normalizar_utc(a.registrado_en),
        )

        ultimos: dict[date, float] = {}
        for a in ordenados:
            ena = a.energia_activa_neta
            if ena is None:
                continue
            local = AgregacionEnergiaService._normalizar_utc(a.registrado_en).astimezone(zona)
            if granularidad == GranularidadEnergia.DIA:
                periodo = local.date()
            else:
                periodo = local.date().replace(day=1)
            ultimos[periodo] = ena.kwh

        resultado: list[EnergiaAgregada] = []
        anterior: float | None = None
        periodo_anterior: date | None = None
        for periodo in sorted(ultimos):
            kwh = ultimos[periodo]
            delta = None if anterior is None else round(kwh - anterior, 3)
            sin_datos = (
                0
                if periodo_anterior is None
                else AgregacionEnergiaService._periodos_entre(periodo_anterior, periodo, granularidad)
            )
            resultado.append(
                EnergiaAgregada(periodo=periodo, energia_activa_neta_kwh=delta, periodos_sin_datos_previos=sin_datos)
            )
            anterior = kwh
            periodo_anterior = periodo
        return resultado

    @staticmethod
    def _periodos_entre(anterior: date, actual: date, granularidad: GranularidadEnergia) -> int:
        """Periodos completos estrictamente entre ``anterior`` y ``actual`` (0 si son consecutivos).

        Con un acumulado por periodo (el último), un hueco que no cubre un periodo entero no se
        puede detectar: solo se marcan los periodos sin ningún dato.
        """
        if granularidad == GranularidadEnergia.DIA:
            return max(0, (actual - anterior).days - 1)
        return max(0, (actual.year - anterior.year) * 12 + actual.month - anterior.month - 1)


class FiltroDeduplicacionService:
    """Filtro de deduplicación de mensajes MQTT (at-least-once → exactly-once).

    Registra las claves vistas y descarta las que se repiten dentro de la
    ventana temporal configurada. Thread-safe vía un ``threading.Lock`` interno.
    """

    def __init__(self, ventana_segundos: int = 120) -> None:
        self._ventana_segundos = ventana_segundos
        self._vistos: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def es_duplicado(self, clave: str, ahora: datetime | None = None) -> bool:
        """Retorna ``True`` si ``clave`` ya fue vista dentro de la ventana.

        En caso contrario, la registra y retorna ``False``. Poda las entradas
        vencidas en cada invocación.
        """
        if ahora is None:
            ahora = datetime.now(timezone.utc)
        with self._lock:
            self._podar(ahora)
            if clave in self._vistos:
                return True
            self._vistos[clave] = ahora
            return False

    def limpiar(self) -> None:
        """Vacía el registro de claves vistas."""
        with self._lock:
            self._vistos.clear()

    def _podar(self, ahora: datetime) -> None:
        limite = ahora - timedelta(seconds=self._ventana_segundos)
        self._vistos = {k: v for k, v in self._vistos.items() if v > limite}

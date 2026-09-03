import threading
from datetime import datetime
from typing import Any

from src.domain.disponibilidad.value_objects import EstadoMaquina


class ClasificadorDisponibilidadService:
    """Clasifica el estado instantáneo de una máquina comparando potencia contra un umbral calibrado."""

    @staticmethod
    def evaluar(potencia_w: float, umbral_marcha_w: float) -> EstadoMaquina:
        return EstadoMaquina.MARCHA if potencia_w >= umbral_marcha_w else EstadoMaquina.PARADA


class FiltroPersistenciaEstadoService:
    """Exige que un cambio de estado (marcha↔parada) persista antes de confirmarlo.

    Generaliza para disponibilidad la misma idea anti-transitorios de
    `src.domain.telemetria.services.FiltroPersistenciaTemporalService` (evitar que un
    solo pico o dip de potencia dispare un evento), pero parametrizada por máquina:
    cada `Maquina` define su propia ventana de persistencia
    (`ventana_persistencia_lecturas` / `ventana_persistencia_segundos`).
    Thread-safe vía `threading.Lock`.
    """

    def __init__(self) -> None:
        self._pendientes: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def confirmar_cambio(
        self,
        maquina_id: str,
        estado_confirmado: EstadoMaquina | None,
        estado_candidato: EstadoMaquina,
        min_lecturas: int,
        min_segundos: float,
        ahora: datetime,
    ) -> bool:
        """`True` si `estado_candidato` debe reemplazar a `estado_confirmado` ahora."""
        with self._lock:
            if estado_confirmado == estado_candidato:
                self._pendientes.pop(maquina_id, None)
                return False

            pendiente = self._pendientes.get(maquina_id)
            if pendiente is None or pendiente["estado"] != estado_candidato:
                self._pendientes[maquina_id] = {"estado": estado_candidato, "conteo": 1, "desde": ahora}
                return min_lecturas <= 1

            pendiente["conteo"] += 1
            delta_seg = (ahora - pendiente["desde"]).total_seconds()
            if pendiente["conteo"] >= min_lecturas or delta_seg >= min_segundos:
                self._pendientes.pop(maquina_id, None)
                return True
            return False

    def limpiar(self) -> None:
        with self._lock:
            self._pendientes.clear()


class CalibradorUmbralService:
    """Calibra el umbral marcha/parada a partir del histograma de potencia histórica de una máquina.

    Construye un histograma de frecuencias, lo suaviza con un promedio móvil (para no
    confundir ruido estadístico con una forma real) y busca el valle entre los dos
    picos principales (parada/standby y marcha) — la misma idea que el método de Otsu
    en procesamiento de imágenes. Sin numpy/scipy: el dominio es stdlib puro (ver
    CONVENTIONS.md), igual que el resto de `src/domain/telemetria/services.py`.

    Devuelve `None` cuando la distribución no muestra una forma bimodal clara: no se
    fuerza un umbral sobre datos que no lo sostienen. En ese caso corresponde
    calibración manual (`PATCH /maquinas/{id}` con `umbral_marcha_w` explícito).
    """

    MIN_LECTURAS = 20
    PROMINENCIA_MINIMA = 0.75
    """El valle debe caer por debajo de esta fracción del pico menor para contar como dip real."""

    @staticmethod
    def _construir_bins(lecturas_w: list[float], num_bins: int) -> tuple[list[float], list[int]]:
        minimo, maximo = min(lecturas_w), max(lecturas_w)
        if maximo <= minimo:
            return [minimo], [len(lecturas_w)]
        ancho = (maximo - minimo) / num_bins
        conteos = [0] * num_bins
        for valor in lecturas_w:
            indice = min(int((valor - minimo) / ancho), num_bins - 1)
            conteos[indice] += 1
        bordes = [minimo + i * ancho for i in range(num_bins)]
        return bordes, conteos

    @staticmethod
    def _suavizar(conteos: list[int], ventana: int = 3) -> list[float]:
        if ventana < 2 or len(conteos) < ventana:
            return [float(c) for c in conteos]
        radio = ventana // 2
        suavizados = []
        for i in range(len(conteos)):
            desde = max(0, i - radio)
            hasta = min(len(conteos), i + radio + 1)
            valores_ventana = conteos[desde:hasta]
            suavizados.append(sum(valores_ventana) / len(valores_ventana))
        return suavizados

    @classmethod
    def _picos_y_valle(cls, suavizados: list[float]) -> tuple[int, int, int] | None:
        """Devuelve (pico_1, valle, pico_2) por índice, o `None` si no hay dos picos claros."""
        picos: list[int] = []
        for i in range(1, len(suavizados) - 1):
            if suavizados[i] > suavizados[i - 1] and suavizados[i] >= suavizados[i + 1] and suavizados[i] > 0:
                picos.append(i)
        if suavizados and suavizados[0] > 0 and (len(suavizados) < 2 or suavizados[0] >= suavizados[1]):
            picos.insert(0, 0)
        if suavizados and suavizados[-1] > 0 and (len(suavizados) < 2 or suavizados[-1] >= suavizados[-2]):
            picos.append(len(suavizados) - 1)

        picos_unicos = sorted(set(picos))
        if len(picos_unicos) < 2:
            return None

        dos_mas_altos = sorted(picos_unicos, key=lambda i: suavizados[i], reverse=True)[:2]
        pico_a, pico_b = sorted(dos_mas_altos)
        if pico_a == pico_b:
            return None

        indice_valle = min(range(pico_a, pico_b + 1), key=lambda i: suavizados[i])
        if indice_valle == pico_a or indice_valle == pico_b:
            return None

        # Prominencia: el valle debe ser un dip real, no ruido de muestreo entre dos
        # máximos casi iguales de una misma campana (caso unimodal con jitter).
        pico_menor = min(suavizados[pico_a], suavizados[pico_b])
        if suavizados[indice_valle] > pico_menor * cls.PROMINENCIA_MINIMA:
            return None

        return pico_a, indice_valle, pico_b

    @classmethod
    def construir_histograma(cls, lecturas_w: list[float], num_bins: int = 40) -> tuple[list[float], list[int]]:
        """Bordes de bins y frecuencias, vacíos si no hay suficientes lecturas para ser representativo."""
        if len(lecturas_w) < cls.MIN_LECTURAS:
            return [], []
        return cls._construir_bins(lecturas_w, num_bins)

    @classmethod
    def calcular_umbral(cls, lecturas_w: list[float], num_bins: int = 40) -> float | None:
        bordes, conteos = cls.construir_histograma(lecturas_w, num_bins)
        if len(conteos) < 5:
            return None

        suavizados = cls._suavizar(conteos, ventana=3)
        resultado = cls._picos_y_valle(suavizados)
        if resultado is None:
            return None

        _, indice_valle, _ = resultado
        ancho_bin = bordes[1] - bordes[0] if len(bordes) > 1 else 0.0
        return round(bordes[indice_valle] + ancho_bin / 2.0, 2)

"""src/domain/telemetria/servicios/potencia_referencia.py — Potencia de referencia del eje Y.

Es el P99 de la potencia activa de un medidor (o de la serie sumada de un nodo) en una ventana fija
de 30 días, para que el frontend fije la escala vertical al navegar entre ventanas. Se usa el P99 y
no el máximo para que un transitorio aislado no aplaste la escala.
"""

from datetime import datetime
from statistics import quantiles

VENTANA_REFERENCIA_HORAS = 30 * 24
GRANULARIDAD_REFERENCIA = "5m"
# Con menos de 24 horas con datos, un medidor recién instalado fijaría la escala con un día atípico
# (por ejemplo, la puesta en marcha). Se cuentan horas y no puntos porque el intervalo mínimo del
# plan puede subir la serie de 5 min a 1 h (plan free): 288 puntos serían 24 h o 12 días.
MINIMO_HORAS_CON_DATOS = 24


def percentil_99(valores: list[float]) -> float:
    """P99 con interpolación lineal entre rangos (método "inclusive", el de NumPy por defecto).
    Requiere al menos dos valores."""
    return quantiles(valores, n=100, method="inclusive")[98]


def potencia_referencia(
    muestras: list[tuple[datetime, float]], minimo_horas: int = MINIMO_HORAS_CON_DATOS
) -> float | None:
    """P99 de las potencias de ``muestras`` (momento, W). ``None`` si cubren menos de
    ``minimo_horas`` horas distintas."""
    horas_con_datos = {int(momento.timestamp() // 3600) for momento, _ in muestras}
    if len(horas_con_datos) < max(minimo_horas, 1) or len(muestras) < 2:
        return None
    return percentil_99([valor for _, valor in muestras])

"""src/domain/telemetria/servicios/harmonics_thd.py — THDv y THDi por fase desde el payload de /harmonics.

Puro (stdlib). Mapea por el número de fase del payload (0/1/2 → R/S/T), no por la posición en la lista.
Valores no numéricos, booleanos, no finitos o negativos se descartan por fase. No se descarta por
magnitud: un THDi de 992,5 % se conserva; decidir su fiabilidad es responsabilidad de `calidad_thd_i`.
"""

import math
from dataclasses import dataclass
from typing import Any

_FASE_POR_NUMERO: dict[int, str] = {0: "R", 1: "S", 2: "T"}


@dataclass(frozen=True)
class ThdFase:
    thd_v_pct: float | None = None
    thd_i_pct: float | None = None


def _valor_valido(valor: Any) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    numero = float(valor)
    if not math.isfinite(numero) or numero < 0.0:
        return None
    return numero


def parsear_thd_harmonics(payload: Any) -> dict[str, ThdFase]:
    """Devuelve {fase: ThdFase} solo para las fases con al menos un THD válido. Nunca lanza."""
    if not isinstance(payload, dict):
        return {}
    fases = payload.get("f")
    if not isinstance(fases, list):
        return {}
    resultado: dict[str, ThdFase] = {}
    for entrada in fases:
        if not isinstance(entrada, dict):
            continue
        numero = entrada.get("n")
        if isinstance(numero, bool) or not isinstance(numero, int):
            continue
        fase = _FASE_POR_NUMERO.get(numero)
        if fase is None:
            continue
        thd_v = _valor_valido(entrada.get("THDv"))
        thd_i = _valor_valido(entrada.get("THDi"))
        if thd_v is None and thd_i is None:
            continue
        resultado[fase] = ThdFase(thd_v_pct=thd_v, thd_i_pct=thd_i)
    return resultado

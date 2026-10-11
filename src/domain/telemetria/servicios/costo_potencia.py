"""src/domain/telemetria/servicios/costo_potencia.py — Costo de la potencia según el esquema tarifario (M-2).

Dominio puro: solo stdlib. Cada esquema tiene su propia fórmula porque la distribuidora no cobra lo mismo:
- POR_FRANJA (EDELAP T5M12): cada franja se paga contra su contratada, con recargo por exceso.
- CAPACIDAD_UNICA (Edesur T3 MT): capacidad convenida única + adquirida completa + recargo por exceso sobre la CSC.

Los factores de recargo y los precios no se hardcodean: los trae la factura (decisión del dueño, D-C). La fuente
de cada número es la transcripción de la liquidación; en el repo de código solo viven como fixtures de test.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FranjaPotencia:
    """Una franja discriminada (punta o fuera de punta): contrato, demanda máxima del mes y precio por kW."""

    contratada_kw: float
    demanda_kw: float
    precio_por_kw: float


@dataclass(frozen=True)
class DatosPotenciaPorFranja:
    franjas: tuple[FranjaPotencia, ...]
    factor_exceso: float  # 1,5 en EDELAP T5M12 (leído de la factura)


@dataclass(frozen=True)
class DatosCapacidadUnica:
    csc_kw: float  # capacidad convenida única
    adquirida_kw: float  # máxima registrada del mes (lectura x constante)
    precio_csc: float  # $/kW de la capacidad convenida
    precio_adquirida: float  # $/kW de la adquirida (distinto del de la CSC)
    factor_exceso: float  # 1,5 sobre el exceso hasta el límite (leído de la factura)
    limite_fraccion_csc: float  # 0,5: hasta esa fracción de la CSC rige factor_exceso
    factor_excedente: float  # 2,0 sobre el exceso que supera el límite (Res. ENRE 303/2025, Inc. 5)


def costo_potencia_por_franja(datos: DatosPotenciaPorFranja) -> float:
    """SUM_f [C_f*p_f + factor*max(0, D_f - C_f)*p_f]. Cada franja se compara contra su propia contratada."""
    total = 0.0
    for franja in datos.franjas:
        _validar_no_negativo(franja.contratada_kw, franja.demanda_kw, franja.precio_por_kw)
        exceso = max(0.0, franja.demanda_kw - franja.contratada_kw)
        total += (franja.contratada_kw + datos.factor_exceso * exceso) * franja.precio_por_kw
    return total


def costo_potencia_capacidad_unica(datos: DatosCapacidadUnica) -> float:
    """CSC x p_csc + adquirida x p_adq + recargo. El recargo es sobre el exceso de la adquirida sobre la CSC:
    factor_exceso hasta limite_fraccion_csc x CSC, y factor_excedente por encima. Todo el recargo va a precio CSC.
    Solo usa la CSC: punta y fuera de punta de la acometida no entran acá (sin doble conteo).
    """
    _validar_no_negativo(datos.csc_kw, datos.adquirida_kw, datos.precio_csc, datos.precio_adquirida)
    if datos.csc_kw <= 0:
        raise ValueError("la capacidad convenida debe ser mayor que cero")

    exceso = max(0.0, datos.adquirida_kw - datos.csc_kw)
    tramo_limite = min(exceso, datos.limite_fraccion_csc * datos.csc_kw)
    tramo_excedente = exceso - tramo_limite
    recargo = (datos.factor_exceso * tramo_limite + datos.factor_excedente * tramo_excedente) * datos.precio_csc

    return datos.csc_kw * datos.precio_csc + datos.adquirida_kw * datos.precio_adquirida + recargo


def _validar_no_negativo(*valores: float) -> None:
    if any(v < 0 for v in valores):
        raise ValueError("kW y precios no pueden ser negativos")

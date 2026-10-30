"""src/domain/telemetria/tarifas_distribuidora.py.

Tarifas de distribuidora con fuente y vigencia (decisions/2026-10-14_brief-tarifas-distribuidora.md).

Solo entra un valor que se pudo verificar contra la factura original. Lo que no está verificado
no se carga: la búsqueda devuelve None y el cálculo no inventa una cifra.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# Recargo por exceso de potencia: 1,5 x (adquirida - convenida) x valor unitario de capacidad.
FACTOR_RECARGO_EXCESO = Decimal("1.5")
_CENTAVO = Decimal("0.01")


@dataclass(frozen=True)
class TarifaCapacidad:
    """Precio de capacidad de un período de facturación, con su fuente."""

    distribuidora: str
    tarifa: str
    periodo: str
    fuente_archivo: str
    vigencia_desde: str
    importe_capacidad_convenida_ars: Decimal
    csc_kw: Decimal

    @property
    def valor_unitario_ars_kw(self) -> Decimal:
        """Valor unitario ponderado del período: importe de capacidad convenida / CSC facturada."""
        return self.importe_capacidad_convenida_ars / self.csc_kw


@dataclass(frozen=True)
class RecargoExcesoPotencia:
    """Recargo calculado con la distribuidora y la tarifa visibles, para mostrar junto a la cifra."""

    distribuidora: str
    tarifa: str
    periodo: str
    fuente_archivo: str
    exceso_kw: Decimal
    importe_ars: Decimal


# Edesur T3 MT: factura 2025-07 (LSP A 9904-02469153 17), renglones "Cap.Sum.Conv T3" y
# "Recargo Exceso Potencia T3". Ponderado por el cambio tarifario del 01/07/2025
# (6 días a 4127,92 y 24 días a 4156,04): (6*4127,92 + 24*4156,04) / 30 = 4150,416.
_TARIFAS_CAPACIDAD: tuple[TarifaCapacidad, ...] = (
    TarifaCapacidad(
        distribuidora="Edesur",
        tarifa="T3 MT",
        periodo="2025-07",
        fuente_archivo="Cristal Avellaneda - EDESUR/2025-07.pdf",
        vigencia_desde="2025-07-01",
        importe_capacidad_convenida_ars=Decimal("3521212.94"),
        csc_kw=Decimal("848.40"),
    ),
)


def obtener_tarifa_capacidad(distribuidora: str, periodo: str) -> TarifaCapacidad | None:
    """Devuelve la tarifa verificada para la distribuidora y el período, o None si no está cargada."""
    for tarifa in _TARIFAS_CAPACIDAD:
        if tarifa.distribuidora == distribuidora and tarifa.periodo == periodo:
            return tarifa
    return None


# Régimen de energía reactiva 1992 (decisions/2026-10-14_regimen-reactiva-edelap.md): recargo solo
# con tg phi > 0,62. El Subanexo A provincial no se modela: queda como riesgo documentado.
LIMITE_TG_FI_REGIMEN_1992 = Decimal("0.62")
MOTIVO_REACTIVA_NO_VERIFICADA = "tarifa reactiva no verificada"


@dataclass(frozen=True)
class PenalizacionReactiva:
    """Penalización por energía reactiva. importe_ars None = sin precio verificado, con motivo."""

    distribuidora: str
    tarifa: str
    periodo: str
    fuente_archivo: str
    regimen: str
    tg_fi_maximo: Decimal
    importe_ars: Decimal | None
    motivo_sin_precio: str | None


def calcular_penalizacion_reactiva_edelap(
    periodo: str,
    fuente_archivo: str,
    tg_fi_por_bloque: tuple[Decimal, ...],
) -> PenalizacionReactiva:
    """Penalización reactiva de EDELAP T5M12 con el régimen 1992.

    Se evalúa con el tg phi máximo de los bloques (punta, valle, resto): si ninguno supera 0,62,
    la penalización es 0. Si alguno lo supera, no hay precio verificado y queda sin importe.
    """
    tg_fi_maximo = max(tg_fi_por_bloque)
    base = {
        "distribuidora": "EDELAP",
        "tarifa": "T5M12",
        "periodo": periodo,
        "fuente_archivo": fuente_archivo,
        "regimen": "contrato nacional 1992 (tg phi <= 0,62)",
        "tg_fi_maximo": tg_fi_maximo,
    }
    if tg_fi_maximo <= LIMITE_TG_FI_REGIMEN_1992:
        return PenalizacionReactiva(importe_ars=Decimal("0.00"), motivo_sin_precio=None, **base)
    return PenalizacionReactiva(importe_ars=None, motivo_sin_precio=MOTIVO_REACTIVA_NO_VERIFICADA, **base)


def calcular_recargo_exceso_potencia(
    csc_kw: Decimal,
    adquirida_kw: Decimal,
    tarifa: TarifaCapacidad | None,
) -> RecargoExcesoPotencia | None:
    """Calcula el recargo por exceso de potencia. Sin tarifa verificada devuelve None."""
    if tarifa is None:
        return None
    exceso_kw = max(adquirida_kw - csc_kw, Decimal("0"))
    importe = (FACTOR_RECARGO_EXCESO * exceso_kw * tarifa.valor_unitario_ars_kw).quantize(
        _CENTAVO, rounding=ROUND_HALF_UP
    )
    return RecargoExcesoPotencia(
        distribuidora=tarifa.distribuidora,
        tarifa=tarifa.tarifa,
        periodo=tarifa.periodo,
        fuente_archivo=tarifa.fuente_archivo,
        exceso_kw=exceso_kw,
        importe_ars=importe,
    )

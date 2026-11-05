"""src/domain/telemetria/tarifas_distribuidora.py.

Tarifas de distribuidora con fuente y vigencia (decisions/2026-10-14_brief-tarifas-distribuidora.md).

Solo entra un valor que se pudo verificar contra la factura original. Lo que no está verificado
no se carga: la búsqueda devuelve None y el cálculo no inventa una cifra.

Desde datamaq#111 este módulo no contiene literales de negocio: las tarifas, el factor de recargo y el
límite de tg phi llegan del puerto `RepositorioParametrosRegulatoriosPort` o por parámetro.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from src.domain.telemetria.parametros_regulatorios import RepositorioParametrosRegulatoriosPort

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


def obtener_tarifa_capacidad(
    repo: RepositorioParametrosRegulatoriosPort, distribuidora: str, periodo: str
) -> TarifaCapacidad | None:
    """Devuelve la tarifa verificada para la distribuidora y el período, o None si no está cargada."""
    return repo.obtener_tarifa_capacidad(distribuidora, periodo)


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
    limite_tg_fi: Decimal,
) -> PenalizacionReactiva:
    """Penalización reactiva de EDELAP T5M12 con el régimen 1992.

    Régimen 1992 (decisions/2026-10-14_regimen-reactiva-edelap.md): recargo solo con tg phi > `limite_tg_fi`
    (0,62 en la carga inicial). Se evalúa con el tg phi máximo de los bloques (punta, valle, resto): si ninguno
    supera el límite, la penalización es 0. Si alguno lo supera, no hay precio verificado y queda sin importe.
    """
    tg_fi_maximo = max(tg_fi_por_bloque)
    base = {
        "distribuidora": "EDELAP",
        "tarifa": "T5M12",
        "periodo": periodo,
        "fuente_archivo": fuente_archivo,
        "regimen": f"contrato nacional 1992 (tg phi <= {str(limite_tg_fi).replace('.', ',')})",
        "tg_fi_maximo": tg_fi_maximo,
    }
    if tg_fi_maximo <= limite_tg_fi:
        return PenalizacionReactiva(importe_ars=Decimal("0.00"), motivo_sin_precio=None, **base)
    return PenalizacionReactiva(importe_ars=None, motivo_sin_precio=MOTIVO_REACTIVA_NO_VERIFICADA, **base)


def calcular_recargo_exceso_potencia(
    csc_kw: Decimal,
    adquirida_kw: Decimal,
    tarifa: TarifaCapacidad | None,
    factor_recargo: Decimal,
) -> RecargoExcesoPotencia | None:
    """Calcula el recargo por exceso de potencia: factor x exceso x valor unitario. Sin tarifa verificada, None."""
    if tarifa is None:
        return None
    exceso_kw = max(adquirida_kw - csc_kw, Decimal("0"))
    importe = (factor_recargo * exceso_kw * tarifa.valor_unitario_ars_kw).quantize(_CENTAVO, rounding=ROUND_HALF_UP)
    return RecargoExcesoPotencia(
        distribuidora=tarifa.distribuidora,
        tarifa=tarifa.tarifa,
        periodo=tarifa.periodo,
        fuente_archivo=tarifa.fuente_archivo,
        exceso_kw=exceso_kw,
        importe_ars=importe,
    )

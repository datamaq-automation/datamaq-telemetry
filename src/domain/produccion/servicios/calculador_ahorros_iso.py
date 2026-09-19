"""src/domain/produccion/servicios/calculador_ahorros_iso.py — Cálculo de ahorros y CUSUM frente a EnB congelada (ISO 50006)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LineaBaseCongelada:
    id: str
    nombre: str
    sec_referencia: float
    potencia_base_kw: float
    periodo_referencia_desde: datetime
    periodo_referencia_hasta: datetime
    congelada_en: datetime


@dataclass(frozen=True)
class ResultadoAhorroEnergia:
    energia_real_kwh: float
    energia_esperada_kwh: float
    ahorro_kwh: float
    ahorro_porcentual: float
    es_mejora: bool
    detalle: str


class CalculadorAhorrosIsoService:
    """Calcula ahorros de energía auditables comparando la operación real contra la EnB congelada."""

    @classmethod
    def evaluar_periodo(
        cls,
        linea_base: LineaBaseCongelada,
        unidades_producidas: float,
        horas_periodo: float,
        energia_real_kwh: float,
    ) -> ResultadoAhorroEnergia:
        e_base = linea_base.potencia_base_kw * horas_periodo
        e_produccion = linea_base.sec_referencia * max(0.0, unidades_producidas)
        e_esperada = round(e_base + e_produccion, 3)

        ahorro_kwh = round(e_esperada - energia_real_kwh, 3)
        ahorro_pct = round(ahorro_kwh / e_esperada, 4) if e_esperada > 0.0 else 0.0
        es_mejora = ahorro_kwh > 0.0

        if es_mejora:
            detalle = f"Mejora de desempeño energético: ahorro de {ahorro_kwh:.1f} kWh ({ahorro_pct:.1%})."
        elif ahorro_kwh < 0.0:
            detalle = f"Degradación de desempeño: sobreconsumo de {abs(ahorro_kwh):.1f} kWh ({abs(ahorro_pct):.1%})."
        else:
            detalle = "Desempeño idéntico a la Línea de Base de referencia."

        return ResultadoAhorroEnergia(
            energia_real_kwh=round(energia_real_kwh, 3),
            energia_esperada_kwh=e_esperada,
            ahorro_kwh=ahorro_kwh,
            ahorro_porcentual=ahorro_pct,
            es_mejora=es_mejora,
            detalle=detalle,
        )

    @staticmethod
    def calcular_cusum(ahorros: list[float]) -> list[float]:
        """Calcula la suma acumulada de ahorros (CUSUM) para auditoría de mejora continua."""
        acumulado = 0.0
        serie_cusum: list[float] = []
        for a in ahorros:
            acumulado = round(acumulado + a, 3)
            serie_cusum.append(acumulado)
        return serie_cusum

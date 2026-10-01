"""src/domain/telemetria/analizador_reactiva.py."""

import math


class DimensionadorCompensacionService:
    """Servicio de dominio puro para el dimensionamiento de compensación de potencia reactiva

    y estimación de penalizaciones tarifarias por bajo factor de potencia (ENRE/distribuidoras).
    """

    ESCALONES_COMERCIALES: tuple[float, ...] = (
        2.5,
        5.0,
        7.5,
        10.0,
        12.5,
        15.0,
        20.0,
        25.0,
        30.0,
        40.0,
        50.0,
        60.0,
        75.0,
        80.0,
        90.0,
        100.0,
        120.0,
        150.0,
        175.0,
        200.0,
        225.0,
        250.0,
        300.0,
        350.0,
        400.0,
        450.0,
        500.0,
        600.0,
        700.0,
        800.0,
        900.0,
        1000.0,
    )

    @staticmethod
    def calcular_potencia_compensacion(
        potencia_activa_kw: float | None,
        fp_actual: float | None,
        fp_objetivo: float = 0.96,
        q_reactiva_kvar: float | None = None,
    ) -> float | None:
        """Calcula la potencia reactiva capacitiva requerida Qc (kVAr) para elevar el FP al objetivo.

        Fórmula:
            Qc = P_activa * (tan(arccos(FP_actual)) - tan(arccos(FP_objetivo)))
            donde tan(arccos(fp)) = sqrt(1 - fp^2) / fp

        Si q_reactiva_kvar es pasado y es <= 0 (capacitivo/sobrecompensado), retorna 0.0
        indicando que no se requiere compensación adicional.
        """
        if potencia_activa_kw is None or fp_actual is None:
            return None
        if potencia_activa_kw <= 0.0 or fp_actual <= 0.0 or fp_actual > 1.0 or fp_objetivo <= 0.0 or fp_objetivo > 1.0:
            return None

        if q_reactiva_kvar is not None and q_reactiva_kvar <= 0.0:
            return 0.0

        # Si el factor de potencia actual ya alcanza o supera el objetivo, no se requiere compensación
        if fp_actual >= fp_objetivo:
            return 0.0

        tan_phi_actual = math.sqrt(1.0 - fp_actual**2) / fp_actual
        tan_phi_objetivo = math.sqrt(1.0 - fp_objetivo**2) / fp_objetivo

        qc = potencia_activa_kw * (tan_phi_actual - tan_phi_objetivo)
        return round(max(0.0, qc), 2)

    @classmethod
    def sugerir_banco_comercial(cls, qc_kvar: float | None) -> float | None:
        """Determina el valor normalizado comercial de banco de capacitores más cercano (>= Qc)."""
        if qc_kvar is None or qc_kvar <= 0.0:
            return None

        for escalon in cls.ESCALONES_COMERCIALES:
            if escalon >= qc_kvar:
                return escalon

        # Para capacidades superiores a 1000 kVAr, redondear al múltiplo superior de 50 kVAr
        return float(math.ceil(qc_kvar / 50.0) * 50.0)

    @classmethod
    def calcular_escalones_sugeridos(cls, qc_kvar: float | None, paso_modular_kvar: float = 12.5) -> list[float]:
        """Calcula la distribución de escalones recomendada para el banco comercial sugerido."""
        banco = cls.sugerir_banco_comercial(qc_kvar)
        if banco is None or banco <= 0.0:
            return []

        if banco <= 25.0:
            return [banco]

        paso = paso_modular_kvar
        if banco >= 100.0:
            paso = 25.0
        if banco >= 300.0:
            paso = 50.0

        escalones: list[float] = []
        remanente = banco
        while remanente > 0.0:
            actual = min(remanente, paso)
            escalones.append(round(actual, 2))
            remanente -= actual

        return escalones

    @staticmethod
    def estimar_penalizacion_mensual_ars(
        potencia_activa_kw: float | None,
        fp_actual: float | None,
        horas_mes: float = 720.0,
        tarifa_kwh_ars: float = 95.0,
        cargo_potencia_kw_ars: float = 1500.0,
    ) -> float | None:
        """Estima el recargo monetario mensual en la factura (ARS) si el FP permanece bajo el umbral de penalidad (0.95).

        Regulación ENRE / Tarifas industriales T2 / T3:
            Recargo (%) = (0.95 / FP_actual - 1) * 100
            Penalización ($) = Costo_Factura_Base * (0.95 / FP_actual - 1)
        """
        if potencia_activa_kw is None or fp_actual is None:
            return None
        if potencia_activa_kw <= 0.0 or fp_actual <= 0.0 or fp_actual > 1.0:
            return None

        # Si el FP no está bajo el umbral de penalidad (0.95), el recargo es 0
        if fp_actual >= 0.95:
            return 0.0

        factor_recargo = (0.95 / fp_actual) - 1.0
        costo_energia = potencia_activa_kw * horas_mes * tarifa_kwh_ars
        costo_potencia = potencia_activa_kw * cargo_potencia_kw_ars
        costo_base = costo_energia + costo_potencia

        recargo_ars = costo_base * factor_recargo
        return round(max(0.0, recargo_ars), 2)

    @staticmethod
    def es_sobrecompensacion_sostenida(q_max_kvar: float | None) -> bool:
        """Determina si existe sobrecompensación reactiva sostenida (Q_max <= 0)."""
        if q_max_kvar is None:
            return False
        return q_max_kvar <= 0.0

    @classmethod
    def evaluar_compensacion(
        cls,
        potencia_activa_kw: float | None,
        fp_actual: float | None,
        q_reactiva_kvar: float | None = None,
        q_max_kvar: float | None = None,
        fp_objetivo: float = 0.96,
    ) -> tuple[float | None, float | None, list[float], bool]:
        """Evalúa dimensionamiento y sobrecompensación sostenida.

        Retorna:
            (qc_kvar, banco_sugerido_kvar, escalones, sobrecompensacion_sostenida)
        """
        sobrecompensacion = cls.es_sobrecompensacion_sostenida(q_max_kvar)
        if sobrecompensacion:
            return 0.0, None, [], True

        qc = cls.calcular_potencia_compensacion(
            potencia_activa_kw=potencia_activa_kw,
            fp_actual=fp_actual,
            fp_objetivo=fp_objetivo,
            q_reactiva_kvar=q_reactiva_kvar,
        )
        if qc is None or qc <= 0.0:
            return qc, None, [], sobrecompensacion

        banco = cls.sugerir_banco_comercial(qc)
        escalones = cls.calcular_escalones_sugeridos(qc) if banco is not None else []
        return qc, banco, escalones, False

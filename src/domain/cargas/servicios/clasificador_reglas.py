"""src/domain/cargas/servicios/clasificador_reglas.py — Clasificador heurístico basado en reglas físicas deterministas (NILM por reglas)."""

from src.domain.cargas.value_objects import (
    CategoriaCarga,
    DiagnosticoReglasCarga,
    EpisodioCarga,
    NaturalezaElectrica,
)


class ClasificadorCargasReglasService:
    """Aplica reglas físicas y temporales para discriminar electrodomésticos y familias de cargas."""

    RATIO_MOTOR_MINIMO = 0.30
    RATIO_RESISTIVO_MAXIMO = 0.18
    PISO_REACTIVA_MOTOR_VAR = 40.0

    @classmethod
    def inferir_naturaleza(cls, episodio: EpisodioCarga) -> NaturalezaElectrica:
        ratio = episodio.ratio_reactiva
        q_abs = abs(episodio.delta_reactiva_var or 0.0)
        p = episodio.delta_w

        if p <= 90.0 and q_abs < cls.PISO_REACTIVA_MOTOR_VAR:
            return NaturalezaElectrica.ELECTRONICA

        if ratio is not None:
            if ratio >= cls.RATIO_MOTOR_MINIMO and q_abs >= cls.PISO_REACTIVA_MOTOR_VAR:
                return NaturalezaElectrica.MOTOR
            if ratio <= cls.RATIO_RESISTIVO_MAXIMO:
                return NaturalezaElectrica.RESISTIVA
            if p <= 450.0:
                return NaturalezaElectrica.ELECTRONICA
            return NaturalezaElectrica.MIXTA

        if episodio.factor_potencia is not None:
            if episodio.factor_potencia <= 0.85 and p > 90.0:
                return NaturalezaElectrica.MOTOR
            if episodio.factor_potencia >= 0.96:
                return NaturalezaElectrica.RESISTIVA
            if p <= 450.0:
                return NaturalezaElectrica.ELECTRONICA

        return NaturalezaElectrica.MIXTA

    @classmethod
    def _clasificar_iluminacion(cls, p: float, q: float, reglas: list[str]) -> DiagnosticoReglasCarga | None:
        if p <= 90.0 and q <= cls.PISO_REACTIVA_MOTOR_VAR:
            reglas.append(f"Baja potencia plana ({p:.0f} W) compatible con circuito de iluminación LED")
            return DiagnosticoReglasCarga(
                aparato_sugerido="Iluminación",
                categoria=CategoriaCarga.ILUMINACION,
                naturaleza_electrica=NaturalezaElectrica.ELECTRONICA,
                confianza=0.85,
                reglas_aplicadas=tuple(reglas),
                es_ambiguo=False,
            )
        return None

    @classmethod
    def _clasificar_motor(
        cls, p: float, t: float, q: float, ratio_q: float | None, reglas: list[str]
    ) -> DiagnosticoReglasCarga:
        ratio_str = f"{ratio_q:.2f}" if ratio_q is not None else "N/A"
        reglas.append(f"Reactiva inductiva significativa (Q={q:.0f} VAr, Q/P={ratio_str})")

        if 70.0 <= p <= 270.0:
            if 135.0 <= p <= 155.0:
                reglas.append("Potencia en rango de solape entre heladera estándar y freezer")
                return DiagnosticoReglasCarga(
                    aparato_sugerido="Refrigeración (Heladera/Freezer)",
                    categoria=CategoriaCarga.REFRIGERACION,
                    naturaleza_electrica=NaturalezaElectrica.MOTOR,
                    confianza=0.70,
                    reglas_aplicadas=tuple(reglas),
                    es_ambiguo=True,
                    alternativas=("Heladera", "Freezer"),
                )

            if p < 135.0 or (p <= 145.0 and t <= 1800.0):
                reglas.append(f"Potencia típica de heladera doméstica ({p:.0f} W) con ciclo de {t / 60:.0f} min")
                return DiagnosticoReglasCarga(
                    aparato_sugerido="Heladera",
                    categoria=CategoriaCarga.REFRIGERACION,
                    naturaleza_electrica=NaturalezaElectrica.MOTOR,
                    confianza=0.88,
                    reglas_aplicadas=tuple(reglas),
                    es_ambiguo=False,
                    alternativas=("Freezer",),
                )

            reglas.append(f"Potencia típica de compresor de freezer ({p:.0f} W) con ciclo de {t / 60:.0f} min")
            return DiagnosticoReglasCarga(
                aparato_sugerido="Freezer",
                categoria=CategoriaCarga.REFRIGERACION,
                naturaleza_electrica=NaturalezaElectrica.MOTOR,
                confianza=0.88,
                reglas_aplicadas=tuple(reglas),
                es_ambiguo=False,
                alternativas=("Heladera",),
            )

        reglas.append(f"Motor o bomba de potencia media/alta ({p:.0f} W)")
        return DiagnosticoReglasCarga(
            aparato_sugerido="Fuerza Motriz / Motor",
            categoria=CategoriaCarga.FUERZA_MOTRIZ,
            naturaleza_electrica=NaturalezaElectrica.MOTOR,
            confianza=0.82,
            reglas_aplicadas=tuple(reglas),
        )

    @classmethod
    def _clasificar_caloventor(cls, p: float, t: float, q: float, reglas: list[str]) -> DiagnosticoReglasCarga | None:
        if (880.0 <= p <= 1150.0 or 1850.0 <= p <= 2150.0) and (20.0 <= q <= 60.0 or t >= 1800.0):
            reglas.append(f"Escalón de climatización ({p:.0f} W) con reactiva leve de ventilador ({q:.0f} VAr)")
            return DiagnosticoReglasCarga(
                aparato_sugerido="Caloventor",
                categoria=CategoriaCarga.CLIMATIZACION,
                naturaleza_electrica=NaturalezaElectrica.MIXTA,
                confianza=0.87,
                reglas_aplicadas=tuple(reglas),
                es_ambiguo=False,
            )
        return None

    @classmethod
    def _clasificar_resistivo(cls, p: float, t: float, q: float, reglas: list[str]) -> DiagnosticoReglasCarga | None:
        reglas.append(f"Factor de potencia casi unitario y reactiva despreciable ({q:.0f} VAr)")

        if 1400.0 <= p <= 2400.0 and t <= 360.0:
            reglas.append(f"Pulso manual ultra-corto de ebullición ({t:.0f} s <= 360 s) a {p:.0f} W")
            return DiagnosticoReglasCarga(
                aparato_sugerido="Pava eléctrica",
                categoria=CategoriaCarga.COCCION,
                naturaleza_electrica=NaturalezaElectrica.RESISTIVA,
                confianza=0.95,
                reglas_aplicadas=tuple(reglas),
                es_ambiguo=False,
            )

        if 900.0 <= p <= 2200.0 and 360.0 < t <= 1500.0:
            reglas.append(f"Cocción por pulsos o duración media de hornalla ({t / 60:.1f} min)")
            return DiagnosticoReglasCarga(
                aparato_sugerido="Anafe eléctrico",
                categoria=CategoriaCarga.COCCION,
                naturaleza_electrica=NaturalezaElectrica.RESISTIVA,
                confianza=0.86,
                reglas_aplicadas=tuple(reglas),
                es_ambiguo=False,
            )

        if 1300.0 <= p <= 2500.0 and 1500.0 < t <= 4000.0:
            reglas.append(f"Bloque largo continuo de calentamiento de agua ({t / 60:.0f} min) a {p:.0f} W")
            return DiagnosticoReglasCarga(
                aparato_sugerido="Termotanque eléctrico",
                categoria=CategoriaCarga.CALENTAMIENTO_AGUA,
                naturaleza_electrica=NaturalezaElectrica.RESISTIVA,
                confianza=0.89,
                reglas_aplicadas=tuple(reglas),
                es_ambiguo=False,
            )

        if 1600.0 <= p <= 3200.0 and t > 4000.0:
            reglas.append(f"Ciclo culinario prolongado de horno ({t / 60:.0f} min) a {p:.0f} W")
            return DiagnosticoReglasCarga(
                aparato_sugerido="Horno eléctrico",
                categoria=CategoriaCarga.COCCION,
                naturaleza_electrica=NaturalezaElectrica.RESISTIVA,
                confianza=0.88,
                reglas_aplicadas=tuple(reglas),
                es_ambiguo=False,
            )

        return None

    @classmethod
    def _clasificar_electronica_pc(
        cls, p: float, t: float, dispersion: float | None, reglas: list[str]
    ) -> DiagnosticoReglasCarga | None:
        if 95.0 < p <= 450.0:
            es_pc_por_variabilidad = dispersion is not None and (dispersion >= 12.0 or (dispersion / p) >= 0.08)
            if es_pc_por_variabilidad or t >= 3600.0:
                reglas.append(
                    f"Fuente conmutada de {p:.0f} W con variabilidad dinámica de régimen ({dispersion or 0:.1f} W)"
                )
                return DiagnosticoReglasCarga(
                    aparato_sugerido="Computadora / PC",
                    categoria=CategoriaCarga.OTROS,
                    naturaleza_electrica=NaturalezaElectrica.ELECTRONICA,
                    confianza=0.83,
                    reglas_aplicadas=tuple(reglas),
                    es_ambiguo=False,
                )
        return None

    @classmethod
    def clasificar_episodio(cls, episodio: EpisodioCarga) -> DiagnosticoReglasCarga:
        p = episodio.delta_w
        t = episodio.duracion_s
        q = abs(episodio.delta_reactiva_var or 0.0)
        ratio_q = episodio.ratio_reactiva
        dispersion = episodio.dispersion_w
        reglas: list[str] = []

        naturaleza = cls.inferir_naturaleza(episodio)

        if diag := cls._clasificar_iluminacion(p, q, reglas):
            return diag

        if naturaleza == NaturalezaElectrica.MOTOR:
            return cls._clasificar_motor(p, t, q, ratio_q, reglas)

        if diag := cls._clasificar_caloventor(p, t, q, reglas):
            return diag

        if naturaleza == NaturalezaElectrica.RESISTIVA or (
            ratio_q is not None and ratio_q <= cls.RATIO_RESISTIVO_MAXIMO
        ):
            if diag := cls._clasificar_resistivo(p, t, q, reglas):
                return diag

        if diag := cls._clasificar_electronica_pc(p, t, dispersion, reglas):
            return diag

        reglas.append(f"Sin coincidencia estricta de regla para P={p:.0f} W, t={t:.0f} s, Q={q:.0f} VAr")
        return DiagnosticoReglasCarga(
            aparato_sugerido="Carga no clasificada",
            categoria=CategoriaCarga.OTROS,
            naturaleza_electrica=naturaleza,
            confianza=0.30,
            reglas_aplicadas=tuple(reglas),
            es_ambiguo=True,
        )

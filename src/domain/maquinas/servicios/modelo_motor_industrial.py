"""src/domain/maquinas/servicios/modelo_motor_industrial.py — Modelo electromecánico determinístico para maquinaria y motores industriales."""

import math
from dataclasses import dataclass
from enum import Enum

from src.domain.maquinas.value_objects import FirmaCarga, OrigenFirma


class RegimenMotorIndustrial(str, Enum):
    APAGADO = "APAGADO"
    VACIO = "VACIO"
    CARGA_PARCIAL = "CARGA_PARCIAL"
    PLENA_CARGA = "PLENA_CARGA"
    SOBRECARGA = "SOBRECARGA"
    NO_COINCIDE = "NO_COINCIDE"


@dataclass(frozen=True)
class DiagnosticoMotorIndustrial:
    regimen: RegimenMotorIndustrial
    factor_carga: float
    cos_phi: float | None
    confianza: float
    es_compatible: bool
    detalle: str


class ModeloMotorFisicoService:
    """Modela el comportamiento electromecánico de motores asíncronos trifásicos industriales según placa."""

    TECHO_VACIO_LF = 0.15
    PISO_VACIO_LF = 0.02
    TECHO_CARGA_PARCIAL_LF = 0.80
    TECHO_NOMINAL_LF = 1.15
    TECHO_SOBRECARGA_LF = 1.80

    COS_PHI_MAX_VACIO = 0.40
    COS_PHI_MIN_NOMINAL = 0.75

    @staticmethod
    def calcular_cos_phi(p_w: float, q_var: float | None) -> float | None:
        if q_var is None or p_w <= 0.0:
            return None
        s = math.hypot(p_w, q_var)
        return round(p_w / s, 4) if s > 0.0 else None

    @classmethod
    def _evaluar_baja_potencia(
        cls, p: float, p_nom: float, lf: float, cos_phi: float | None, q: float | None
    ) -> DiagnosticoMotorIndustrial:
        if p <= 20.0 and (q is None or abs(q) <= 50.0):
            return DiagnosticoMotorIndustrial(
                regimen=RegimenMotorIndustrial.APAGADO,
                factor_carga=lf,
                cos_phi=cos_phi,
                confianza=0.90,
                es_compatible=True,
                detalle="Potencia casi nula, motor apagado.",
            )
        return DiagnosticoMotorIndustrial(
            regimen=RegimenMotorIndustrial.NO_COINCIDE,
            factor_carga=lf,
            cos_phi=cos_phi,
            confianza=0.10,
            es_compatible=False,
            detalle=f"Potencia ({p:.0f} W) incompatiblemente baja para motor de {p_nom:.0f} W.",
        )

    @classmethod
    def _evaluar_vacio(cls, lf: float, cos_phi: float | None) -> DiagnosticoMotorIndustrial:
        if cos_phi is not None and cos_phi > 0.60:
            return DiagnosticoMotorIndustrial(
                regimen=RegimenMotorIndustrial.NO_COINCIDE,
                factor_carga=lf,
                cos_phi=cos_phi,
                confianza=0.20,
                es_compatible=False,
                detalle="Factor de potencia excesivamente alto para un motor en vacío (esperado < 0.40).",
            )
        conf = 0.88 if (cos_phi is not None and cos_phi <= cls.COS_PHI_MAX_VACIO) else 0.70
        return DiagnosticoMotorIndustrial(
            regimen=RegimenMotorIndustrial.VACIO,
            factor_carga=lf,
            cos_phi=cos_phi,
            confianza=conf,
            es_compatible=True,
            detalle=f"Motor en vacío (LF={lf:.1%}). Activa baja y reactiva de magnetización presente.",
        )

    @classmethod
    def _evaluar_carga_activa(cls, lf: float, cos_phi: float | None) -> DiagnosticoMotorIndustrial:
        if lf <= cls.TECHO_CARGA_PARCIAL_LF:
            if cos_phi is not None and cos_phi >= 0.98:
                return DiagnosticoMotorIndustrial(
                    regimen=RegimenMotorIndustrial.NO_COINCIDE,
                    factor_carga=lf,
                    cos_phi=cos_phi,
                    confianza=0.15,
                    es_compatible=False,
                    detalle="Máquina puramente resistiva detectada, incompatible con motor de inducción a media carga.",
                )
            return DiagnosticoMotorIndustrial(
                regimen=RegimenMotorIndustrial.CARGA_PARCIAL,
                factor_carga=lf,
                cos_phi=cos_phi,
                confianza=0.85,
                es_compatible=True,
                detalle=f"Motor en carga parcial (LF={lf:.1%}).",
            )
        if lf <= cls.TECHO_NOMINAL_LF:
            return DiagnosticoMotorIndustrial(
                regimen=RegimenMotorIndustrial.PLENA_CARGA,
                factor_carga=lf,
                cos_phi=cos_phi,
                confianza=0.92,
                es_compatible=True,
                detalle=f"Motor a plena carga (LF={lf:.1%}).",
            )
        if lf <= cls.TECHO_SOBRECARGA_LF:
            return DiagnosticoMotorIndustrial(
                regimen=RegimenMotorIndustrial.SOBRECARGA,
                factor_carga=lf,
                cos_phi=cos_phi,
                confianza=0.80,
                es_compatible=True,
                detalle=f"Motor en sobrecarga admisible (LF={lf:.1%}).",
            )
        return DiagnosticoMotorIndustrial(
            regimen=RegimenMotorIndustrial.NO_COINCIDE,
            factor_carga=lf,
            cos_phi=cos_phi,
            confianza=0.10,
            es_compatible=False,
            detalle=f"Potencia excede ampliamente la capacidad del motor (LF={lf:.1%}).",
        )

    @classmethod
    def estimar_regimen(
        cls,
        potencia_w: float,
        potencia_nominal_w: float,
        potencia_reactiva_var: float | None = None,
    ) -> DiagnosticoMotorIndustrial:
        if potencia_nominal_w <= 0.0 or potencia_w < 0.0:
            return DiagnosticoMotorIndustrial(
                regimen=RegimenMotorIndustrial.NO_COINCIDE,
                factor_carga=0.0,
                cos_phi=None,
                confianza=0.0,
                es_compatible=False,
                detalle="Potencia nominal o medida inválida.",
            )

        lf = potencia_w / potencia_nominal_w
        cos_phi = cls.calcular_cos_phi(potencia_w, potencia_reactiva_var)

        if lf < cls.PISO_VACIO_LF:
            return cls._evaluar_baja_potencia(potencia_w, potencia_nominal_w, lf, cos_phi, potencia_reactiva_var)

        if lf <= cls.TECHO_VACIO_LF:
            return cls._evaluar_vacio(lf, cos_phi)

        return cls._evaluar_carga_activa(lf, cos_phi)

    @classmethod
    def generar_firma_desde_chapa(
        cls,
        potencia_nominal_w: float,
        factor_carga_esperado: float = 0.75,
        cos_phi_esperado: float = 0.83,
    ) -> FirmaCarga:
        """Genera una firma sintética calibrada según leyes físicas del motor trifásico."""
        p_activa = round(potencia_nominal_w * factor_carga_esperado, 1)
        # S = P / cos_phi; Q = sqrt(S^2 - P^2)
        s_aparente = p_activa / cos_phi_esperado
        q_reactiva = round(math.sqrt(max(0.0, s_aparente**2 - p_activa**2)), 1)
        dispersion = round(p_activa * 0.10, 1)

        return FirmaCarga(
            potencia_w=p_activa,
            dispersion_w=dispersion,
            potencia_reactiva_var=q_reactiva,
            factor_potencia=cos_phi_esperado,
            origen=OrigenFirma.CHAPA,
        )

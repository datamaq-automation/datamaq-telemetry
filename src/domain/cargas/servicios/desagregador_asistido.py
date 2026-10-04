"""src/domain/cargas/servicios/desagregador_asistido.py — Desagregación de potencia en TGBT asistida por sensórica inductiva."""

from dataclasses import dataclass

from src.domain.cargas.servicios.modelo_motor_industrial import (
    ModeloMotorFisicoService,
    RegimenMotorIndustrial,
)


@dataclass(frozen=True)
class ResultadoDesagregacionAsistida:
    atribuido: bool
    potencia_maquina_w: float
    potencia_residual_w: float
    confianza: float
    motivo: str


class DesagregadorAsistidoService:
    """Desagrega la potencia del transformador/TGBT correlacionando escalones con la actividad de sensores inductivos."""

    @classmethod
    def desagregar_intervalo(
        cls,
        potencia_tgbt_w: float,
        potencia_base_w: float,
        sensor_inductivo_activo: bool,
        potencia_nominal_w: float,
        potencia_reactiva_var: float | None = None,
    ) -> ResultadoDesagregacionAsistida:
        if not sensor_inductivo_activo:
            return ResultadoDesagregacionAsistida(
                atribuido=False,
                potencia_maquina_w=0.0,
                potencia_residual_w=potencia_tgbt_w,
                confianza=0.95,
                motivo="Sensor inactivo: la máquina no está operando.",
            )

        delta_p = max(0.0, potencia_tgbt_w - potencia_base_w)
        diag = ModeloMotorFisicoService.estimar_regimen(
            potencia_w=delta_p,
            potencia_nominal_w=potencia_nominal_w,
            potencia_reactiva_var=potencia_reactiva_var,
        )

        if diag.es_compatible and diag.regimen != RegimenMotorIndustrial.NO_COINCIDE:
            potencia_atribuida = delta_p
            residual = max(0.0, potencia_tgbt_w - potencia_atribuida)
            return ResultadoDesagregacionAsistida(
                atribuido=True,
                potencia_maquina_w=potencia_atribuida,
                potencia_residual_w=residual,
                confianza=diag.confianza,
                motivo=f"Sensor inductivo activo. Incremento compatible con régimen {diag.regimen.value}: {diag.detalle}",
            )

        # Si el sensor está activo pero el delta no coincide exactamente, se atribuye potencia esperada de régimen
        potencia_atribuida = min(delta_p, potencia_nominal_w * 0.75)
        residual = max(0.0, potencia_tgbt_w - potencia_atribuida)
        return ResultadoDesagregacionAsistida(
            atribuido=True,
            potencia_maquina_w=potencia_atribuida,
            potencia_residual_w=residual,
            confianza=0.70,
            motivo=f"Sensor inductivo activo con delta discordante ({delta_p:.0f} W vs {potencia_nominal_w:.0f} W nominal).",
        )

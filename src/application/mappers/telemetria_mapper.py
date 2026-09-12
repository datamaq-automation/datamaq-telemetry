"""src/application/mappers/telemetria_mapper.py."""

from datetime import datetime, timezone

from src.application.dtos.telemetria_dto import (
    AcumuladoEnergiaDTO,
    AnaliticaCalidadEnergiaDTO,
    DiagnosticoFasesDispositivoDTO,
    EnergiaAgregadaDTO,
    LecturaInstantaneaDTO,
    LogEstadoDispositivoDTO,
    MedicionFaseDTO,
)
from src.domain.telemetria.entities import (
    AcumuladoEnergia,
    EnergiaAgregada,
    LecturaInstantanea,
    LogEstadoDispositivo,
    MedicionFase,
)
from src.domain.telemetria.services import (
    AnalizadorCalidadEnergiaService,
    DiagnosticoFasorialRed,
)
from src.domain.telemetria.value_objects import AnaliticaCalidadEnergia


class TelemetriaMapper:
    @staticmethod
    def analitica_to_dto(analitica: AnaliticaCalidadEnergia | None) -> AnaliticaCalidadEnergiaDTO | None:
        if analitica is None:
            return None
        return AnaliticaCalidadEnergiaDTO(
            requiere_compensacion=analitica.requiere_compensacion,
            potencia_reactiva_a_compensar_kvar=analitica.potencia_reactiva_a_compensar_kvar,
            banco_sugerido_kvar=analitica.banco_sugerido_kvar,
            penalizacion_estimada_ars=analitica.penalizacion_estimada_ars,
            desbalance_tension_porcentaje=analitica.desbalance_tension_porcentaje,
            desbalance_corriente_porcentaje=analitica.desbalance_corriente_porcentaje,
            estado_fp=analitica.estado_fp,
            estado_tension=analitica.estado_tension,
            recargo_porcentaje=analitica.recargo_porcentaje,
            motivo_abstencion=analitica.motivo_abstencion,
            ventana_evaluacion_min=analitica.ventana_evaluacion_min,
            vigente_desde=analitica.vigente_desde,
            factor_potencia_integrado=analitica.factor_potencia_integrado,
        )

    @staticmethod
    def fase_to_dto(fase: MedicionFase) -> MedicionFaseDTO:
        return MedicionFaseDTO(
            voltage_V=fase.tension.voltios if fase.tension else None,
            current_A=fase.corriente.amperios if fase.corriente else None,
            net_active_power_W=fase.potencia_activa.vatios if fase.potencia_activa else None,
            net_reactive_power_VAR=fase.potencia_reactiva.var if fase.potencia_reactiva else None,
            net_apparent_power_VA=fase.potencia_aparente.va if fase.potencia_aparente else None,
            power_factor=fase.factor_potencia.valor if fase.factor_potencia else None,
            thd_v_pct=fase.thd_v_porcentaje,
            thd_i_pct=fase.thd_i_porcentaje,
        )

    @staticmethod
    def instantanea_to_dto(
        lectura: LecturaInstantanea,
        analitica: AnaliticaCalidadEnergia | None = None,
    ) -> LecturaInstantaneaDTO:
        if analitica is None:
            analitica = AnalizadorCalidadEnergiaService.calcular_analitica_completa(lectura)

        return LecturaInstantaneaDTO(
            id=lectura.id,
            dispositivo_id=lectura.dispositivo_id,
            registrado_en=lectura.registrado_en,
            fase_r=TelemetriaMapper.fase_to_dto(lectura.fase_r),
            fase_s=TelemetriaMapper.fase_to_dto(lectura.fase_s),
            fase_t=TelemetriaMapper.fase_to_dto(lectura.fase_t),
            potencia_activa_total_W=lectura.potencia_activa_total.vatios if lectura.potencia_activa_total else None,
            potencia_reactiva_total_VAR=lectura.potencia_reactiva_total.var
            if lectura.potencia_reactiva_total
            else None,
            potencia_aparente_total_VA=lectura.potencia_aparente_total.va if lectura.potencia_aparente_total else None,
            factor_potencia_total=lectura.factor_potencia_total.valor if lectura.factor_potencia_total else None,
            desbalance_tension_porcentaje=lectura.desbalance_tension_porcentaje,
            corriente_neutro_estimada_A=lectura.corriente_neutro_estimada.amperios
            if lectura.corriente_neutro_estimada
            else None,
            voltage_linea_V=lectura.voltage_linea_V,
            tension_neutro_estimada_V=lectura.tension_neutro_estimada,
            thd_v_promedio_pct=lectura.thd_v_promedio_porcentaje,
            thd_i_total_pct=lectura.thd_i_total_porcentaje,
            analitica=TelemetriaMapper.analitica_to_dto(analitica),
        )

    @staticmethod
    def acumulado_to_dto(acumulado: AcumuladoEnergia) -> AcumuladoEnergiaDTO:
        return AcumuladoEnergiaDTO(
            id=acumulado.id,
            dispositivo_id=acumulado.dispositivo_id,
            registrado_en=acumulado.registrado_en,
            net_active_energy_kwh=acumulado.energia_activa_neta.kwh if acumulado.energia_activa_neta else None,
            net_reactive_energy_kvarh=acumulado.energia_reactiva_neta.kvarh
            if acumulado.energia_reactiva_neta
            else None,
            imported_active_energy_kwh=acumulado.energia_activa_importada.kwh
            if acumulado.energia_activa_importada
            else None,
            exported_active_energy_kwh=acumulado.energia_activa_exportada.kwh
            if acumulado.energia_activa_exportada
            else None,
            imported_reactive_energy_kvarh=acumulado.energia_reactiva_importada.kvarh
            if acumulado.energia_reactiva_importada
            else None,
            exported_reactive_energy_kvarh=acumulado.energia_reactiva_exportada.kvarh
            if acumulado.energia_reactiva_exportada
            else None,
        )

    @staticmethod
    def energia_agregada_to_dto(agregada: EnergiaAgregada) -> EnergiaAgregadaDTO:
        return EnergiaAgregadaDTO(
            periodo=agregada.periodo,
            energia_activa_neta_kwh=agregada.energia_activa_neta_kwh,
        )

    @staticmethod
    def log_estado_to_dto(log: LogEstadoDispositivo) -> LogEstadoDispositivoDTO:
        return LogEstadoDispositivoDTO(
            id=log.id,
            dispositivo_id=log.dispositivo_id,
            registrado_en=log.registrado_en,
            wifi_rssi_dbm=log.wifi_rssi_dbm,
            wifi_calidad=log.wifi_calidad,
            direccion_ip=log.direccion_ip,
            tiempo_activo_segundos=log.tiempo_activo_segundos,
            payload_bruto=log.payload_bruto,
        )

    @staticmethod
    def diagnostico_fasorial_to_dto(
        diag: DiagnosticoFasorialRed,
    ) -> DiagnosticoFasesDispositivoDTO:
        from src.application.dtos.telemetria_dto import DiagnosticoFaseDTO

        def _map_fase(fase_diag: object) -> DiagnosticoFaseDTO:
            return DiagnosticoFaseDTO(
                fp_original=getattr(fase_diag, "fp_original", None),
                angulo_phi_grados=getattr(fase_diag, "phi_deg_original", None),
                potencia_activa_w=getattr(fase_diag, "potencia_activa_w", None),
                potencia_reactiva_var=getattr(fase_diag, "potencia_reactiva_var", None),
                rotacion_optima_sugerida=getattr(fase_diag, "rotacion_optima_sugerida", None),
                fp_con_rotacion_optima=getattr(fase_diag, "fp_con_rotacion_optima", None),
                potencia_activa_con_rotacion_optima_w=getattr(fase_diag, "p_con_rotacion_optima_w", None),
                potencia_reactiva_con_rotacion_optima_var=getattr(fase_diag, "q_con_rotacion_optima_var", None),
                rotaciones_evaluadas=getattr(fase_diag, "rotaciones_evaluadas", None),
            )

        evaluado = diag.evaluado_en or datetime.now(timezone.utc)
        return DiagnosticoFasesDispositivoDTO(
            dispositivo_id=diag.dispositivo_id,
            evaluado_en=evaluado,
            fase_r=_map_fase(diag.fase_r),
            fase_s=_map_fase(diag.fase_s),
            fase_t=_map_fase(diag.fase_t),
            diagnostico_general=diag.diagnostico_general,
            recomendacion_hardware=diag.recomendacion_hardware,
        )

"""src/application/mappers/telemetria_mapper.py."""

import math
from datetime import datetime, timezone

from src.application.dtos.telemetria_dto import (
    AcumuladoEnergiaDTO,
    AnaliticaCalidadEnergiaDTO,
    DiagnosticoFasesDispositivoDTO,
    DiagnosticoInstalacionDTO,
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


def _calcular_phi_grados(p: float | None, q: float | None) -> float | None:
    if p is None or q is None:
        return None
    if p == 0.0 and q == 0.0:
        return 0.0
    return round(-math.degrees(math.atan2(q, p)), 1)


class TelemetriaMapper:
    @staticmethod
    def analitica_to_dto(analitica: AnaliticaCalidadEnergia | None) -> AnaliticaCalidadEnergiaDTO:
        if analitica is None:
            return AnaliticaCalidadEnergiaDTO(motivo_abstencion="SIN_DATOS")
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
        p = fase.potencia_activa.vatios if fase.potencia_activa else None
        q = fase.potencia_reactiva.var if fase.potencia_reactiva else None
        return MedicionFaseDTO(
            voltage_V=fase.tension.voltios if fase.tension else None,
            current_A=fase.corriente.amperios if fase.corriente else None,
            net_active_power_W=p,
            net_reactive_power_VAR=q,
            net_apparent_power_VA=fase.potencia_aparente.va if fase.potencia_aparente else None,
            power_factor=fase.factor_potencia.valor if fase.factor_potencia else None,
            phi_grados=_calcular_phi_grados(p, q),
            thd_v_pct=fase.thd_v_porcentaje,
            thd_i_pct=fase.thd_i_porcentaje,
            angulo_correccion=fase.angulo_correccion,
        )

    @staticmethod
    def instantanea_to_dto(
        lectura: LecturaInstantanea,
        analitica: AnaliticaCalidadEnergia | None = None,
        dispositivo: object | None = None,
    ) -> LecturaInstantaneaDTO:
        diag_inst_dto: DiagnosticoInstalacionDTO | None = None
        diag_domain = getattr(lectura, "diagnostico_instalacion", None)
        if diag_domain is None and dispositivo is not None:
            from src.domain.telemetria.servicios.evaluador_diagnostico_instalacion import (
                EvaluadorDiagnosticoInstalacionService,
            )

            fases_con_ti = getattr(dispositivo, "fases_con_ti", None)
            fases_list = [f.strip().upper() for f in fases_con_ti.split(",")] if isinstance(fases_con_ti, str) else None
            diag_domain = EvaluadorDiagnosticoInstalacionService.evaluar_diagnostico(
                lectura=lectura,
                fases_con_ti=fases_list,
                dispositivo_id=lectura.dispositivo_id,
            )

        if diag_domain is not None:
            diag_inst_dto = DiagnosticoInstalacionDTO(
                estado_metrologico=diag_domain.estado_metrologico,
                fases_validas=list(diag_domain.fases_validas),
                fases_comprometidas=list(diag_domain.fases_comprometidas),
                anomalias_detectadas=list(diag_domain.anomalias_detectadas),
                potencia_estimada_simetrica_w=diag_domain.potencia_estimada_simetrica_w,
                factor_potencia_estimado_simetrico=diag_domain.factor_potencia_estimado_simetrico,
                accion_correctiva_sugerida=diag_domain.accion_correctiva_sugerida,
            )

        if analitica is None:
            # D-11: sin `dispositivo`, _evaluar_abstencion_enre no puede saber si el
            # circuito está alcanzado por el régimen ENRE 184/2000 — un dispositivo
            # T1-R/monofásico pasaría por acá con requiere_compensacion=true y un
            # monto real en pesos, siendo que está exento por categoría tarifaria.
            # Además se propaga diag_domain para abstención por metrología degradada.
            analitica = AnalizadorCalidadEnergiaService.calcular_analitica_completa(
                lectura, dispositivo=dispositivo, diagnostico_instalacion=diag_domain
            )

        p_tot = lectura.potencia_activa_total.vatios if lectura.potencia_activa_total else None
        q_tot = lectura.potencia_reactiva_total.var if lectura.potencia_reactiva_total else None

        return LecturaInstantaneaDTO(
            id=lectura.id,
            dispositivo_id=lectura.dispositivo_id,
            registrado_en=lectura.registrado_en,
            fase_r=TelemetriaMapper.fase_to_dto(lectura.fase_r),
            fase_s=TelemetriaMapper.fase_to_dto(lectura.fase_s),
            fase_t=TelemetriaMapper.fase_to_dto(lectura.fase_t),
            potencia_activa_total_W=p_tot,
            potencia_reactiva_total_VAR=q_tot,
            potencia_aparente_total_VA=lectura.potencia_aparente_total.va if lectura.potencia_aparente_total else None,
            factor_potencia_total=lectura.factor_potencia_total.valor if lectura.factor_potencia_total else None,
            phi_total_grados=_calcular_phi_grados(p_tot, q_tot),
            desbalance_tension_porcentaje=lectura.desbalance_tension_porcentaje,
            corriente_neutro_estimada_A=lectura.corriente_neutro_estimada.amperios
            if lectura.corriente_neutro_estimada
            else None,
            voltage_linea_V=lectura.voltage_linea_V,
            tension_neutro_estimada_V=lectura.tension_neutro_estimada,
            thd_v_promedio_pct=lectura.thd_v_promedio_porcentaje,
            thd_i_total_pct=lectura.thd_i_total_porcentaje,
            analitica=TelemetriaMapper.analitica_to_dto(analitica),
            diagnostico_instalacion=diag_inst_dto,
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
            fp_orig = getattr(fase_diag, "fp_original", None)
            estado_ti = getattr(fase_diag, "estado_ti", "CORRECTO")
            duplicado_con = None
            if "DUPLICADO" in estado_ti:
                if "Fase S" in estado_ti or "en S" in estado_ti:
                    duplicado_con = "S"
                elif "Fase R" in estado_ti or "en R" in estado_ti:
                    duplicado_con = "R"
            validez = estado_ti == "CORRECTO"
            return DiagnosticoFaseDTO(
                fp_original=fp_orig,
                angulo_phi_grados=getattr(fase_diag, "phi_deg_original", None),
                potencia_activa_w=getattr(fase_diag, "potencia_activa_w", None),
                potencia_reactiva_var=getattr(fase_diag, "potencia_reactiva_var", None),
                rotacion_optima_sugerida=getattr(fase_diag, "rotacion_optima_sugerida", None),
                fp_con_rotacion_optima=getattr(fase_diag, "fp_con_rotacion_optima", None),
                potencia_activa_con_rotacion_optima_w=getattr(fase_diag, "p_con_rotacion_optima_w", None),
                potencia_reactiva_con_rotacion_optima_var=getattr(fase_diag, "q_con_rotacion_optima_var", None),
                rotaciones_evaluadas=getattr(fase_diag, "rotaciones_evaluadas", None),
                tension_v=getattr(fase_diag, "tension_v", None),
                corriente_a=getattr(fase_diag, "corriente_a", None),
                factor_potencia=fp_orig,
                angulo_fasorial_grados=getattr(fase_diag, "angulo_fasorial_grados", None),
                tc_invertido_180=getattr(fase_diag, "tc_invertido_180", False),
                estado_ti=estado_ti,
                duplicado_con_fase=duplicado_con,
                validez_metrologica=validez,
            )

        evaluado = diag.evaluado_en or datetime.now(timezone.utc)
        fase_r_dto = _map_fase(diag.fase_r)
        fase_s_dto = _map_fase(diag.fase_s)
        fase_t_dto = _map_fase(diag.fase_t)

        return DiagnosticoFasesDispositivoDTO(
            dispositivo_id=diag.dispositivo_id,
            evaluado_en=evaluado,
            fase_r=fase_r_dto,
            fase_s=fase_s_dto,
            fase_t=fase_t_dto,
            diagnostico_general=diag.diagnostico_general,
            recomendacion_hardware=diag.recomendacion_hardware,
            fases={
                "R": fase_r_dto,
                "S": fase_s_dto,
                "T": fase_t_dto,
            },
            secuencia_fases=getattr(diag, "secuencia_fases", "DIRECTA"),
            rotacion_correcta=getattr(diag, "rotacion_correcta", True),
            alertas_fasoriales=list(getattr(diag, "alertas_fasoriales", ())),
        )

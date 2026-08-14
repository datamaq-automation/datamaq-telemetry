from src.application.dtos.telemetria_dto import (
    AcumuladoEnergiaDTO,
    LecturaInstantaneaDTO,
    LogEstadoDispositivoDTO,
    MedicionFaseDTO,
)
from src.domain.telemetria.entities import (
    AcumuladoEnergia,
    LecturaInstantanea,
    LogEstadoDispositivo,
    MedicionFase,
)


class TelemetriaMapper:
    @staticmethod
    def fase_to_dto(fase: MedicionFase) -> MedicionFaseDTO:
        return MedicionFaseDTO(
            voltage_V=fase.tension.voltios if fase.tension else None,
            current_A=fase.corriente.amperios if fase.corriente else None,
            net_active_power_W=fase.potencia_activa.vatios if fase.potencia_activa else None,
            net_reactive_power_VAR=fase.potencia_reactiva.var if fase.potencia_reactiva else None,
            net_apparent_power_VA=fase.potencia_aparente.va if fase.potencia_aparente else None,
            power_factor=fase.factor_potencia.valor if fase.factor_potencia else None,
        )

    @staticmethod
    def instantanea_to_dto(lectura: LecturaInstantanea) -> LecturaInstantaneaDTO:
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

from datetime import datetime
from decimal import Decimal

from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from src.domain.telemetria.entities import (
    AcumuladoEnergia,
    AlertaDispositivo,
    LecturaInstantanea,
    LogEstadoDispositivo,
    MedicionFase,
)
from src.domain.telemetria.ports import RepositorioTelemetriaPort
from src.domain.telemetria.value_objects import (
    Corriente,
    EnergiaActiva,
    EnergiaReactiva,
    FactorPotencia,
    LecturaPotenciaTemporal,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    SeveridadAlerta,
    Tension,
)
from src.infrastructure.sqlalchemy.models import (
    DeviceAlertModel,
    DeviceStatusLogModel,
    TelemetryEnergyModel,
    TelemetryInstantaneousModel,
)


class MySQLTelemetriaRepository(RepositorioTelemetriaPort):
    def __init__(self, db: Session):
        self.db = db

    def _to_fase(self, v, i, p, q, s, fp, thd_v=None, thd_i=None) -> MedicionFase:
        return MedicionFase(
            tension=Tension(voltios=float(v)) if v is not None else None,
            corriente=Corriente(amperios=float(i)) if i is not None else None,
            potencia_activa=PotenciaActiva(vatios=float(p)) if p is not None else None,
            potencia_reactiva=PotenciaReactiva(var=float(q)) if q is not None else None,
            potencia_aparente=PotenciaAparente(va=float(s)) if s is not None else None,
            factor_potencia=FactorPotencia(valor=float(fp)) if fp is not None else None,
            thd_v_porcentaje=float(thd_v) if thd_v is not None else None,
            thd_i_porcentaje=float(thd_i) if thd_i is not None else None,
        )

    def _instantanea_to_entity(self, m: TelemetryInstantaneousModel) -> LecturaInstantanea:
        fase_r = self._to_fase(
            m.voltage_r,
            m.current_r,
            m.active_power_r,
            m.reactive_power_r,
            m.apparent_power_r,
            m.power_factor_r,
            getattr(m, "thd_v_r", None),
            getattr(m, "thd_i_r", None),
        )
        fase_s = self._to_fase(
            m.voltage_s,
            m.current_s,
            m.active_power_s,
            m.reactive_power_s,
            m.apparent_power_s,
            m.power_factor_s,
            getattr(m, "thd_v_s", None),
            getattr(m, "thd_i_s", None),
        )
        fase_t = self._to_fase(
            m.voltage_t,
            m.current_t,
            m.active_power_t,
            m.reactive_power_t,
            m.apparent_power_t,
            m.power_factor_t,
            getattr(m, "thd_v_t", None),
            getattr(m, "thd_i_t", None),
        )

        in_obj = None
        if hasattr(m, "current_n") and m.current_n is not None:
            in_obj = Corriente(amperios=float(m.current_n))

        vl_val = float(m.voltage_linea_V) if hasattr(m, "voltage_linea_V") and m.voltage_linea_V is not None else None

        vn_val = (
            float(m.tension_neutro_estimada)
            if hasattr(m, "tension_neutro_estimada") and m.tension_neutro_estimada is not None
            else None
        )

        thd_v_prom_val = (
            float(m.thd_v_promedio_porcentaje)
            if hasattr(m, "thd_v_promedio_porcentaje") and m.thd_v_promedio_porcentaje is not None
            else None
        )
        thd_i_tot_val = (
            float(m.thd_i_total_porcentaje)
            if hasattr(m, "thd_i_total_porcentaje") and m.thd_i_total_porcentaje is not None
            else None
        )

        return LecturaInstantanea(
            id=m.id,
            dispositivo_id=m.device_id,
            registrado_en=m.recorded_at,
            fase_r=fase_r,
            fase_s=fase_s,
            fase_t=fase_t,
            potencia_activa_total=PotenciaActiva(vatios=float(m.total_active_power))
            if m.total_active_power is not None
            else None,
            potencia_reactiva_total=PotenciaReactiva(var=float(m.total_reactive_power))
            if m.total_reactive_power is not None
            else None,
            potencia_aparente_total=PotenciaAparente(va=float(m.total_apparent_power))
            if m.total_apparent_power is not None
            else None,
            factor_potencia_total=FactorPotencia(valor=float(m.total_power_factor))
            if m.total_power_factor is not None
            else None,
            desbalance_tension_porcentaje=float(m.desbalance_tension_porcentaje)
            if m.desbalance_tension_porcentaje is not None
            else None,
            corriente_neutro_estimada=in_obj,
            voltage_linea_V=vl_val,
            tension_neutro_estimada=vn_val,
            thd_v_promedio_porcentaje=thd_v_prom_val,
            thd_i_total_porcentaje=thd_i_tot_val,
        )

    def _energia_to_entity(self, m: TelemetryEnergyModel) -> AcumuladoEnergia:
        return AcumuladoEnergia(
            id=m.id,
            dispositivo_id=m.device_id,
            registrado_en=m.recorded_at,
            energia_activa_neta=EnergiaActiva(kwh=float(m.net_active_energy_kwh))
            if m.net_active_energy_kwh is not None
            else None,
            energia_reactiva_neta=EnergiaReactiva(kvarh=float(m.net_reactive_energy_kvarh))
            if m.net_reactive_energy_kvarh is not None
            else None,
            energia_activa_importada=EnergiaActiva(kwh=float(m.imported_active_energy_kwh))
            if m.imported_active_energy_kwh is not None
            else None,
            energia_activa_exportada=EnergiaActiva(kwh=float(m.exported_active_energy_kwh))
            if m.exported_active_energy_kwh is not None
            else None,
            energia_reactiva_importada=EnergiaReactiva(kvarh=float(m.imported_reactive_energy_kvarh))
            if m.imported_reactive_energy_kvarh is not None
            else None,
            energia_reactiva_exportada=EnergiaReactiva(kvarh=float(m.exported_reactive_energy_kvarh))
            if m.exported_reactive_energy_kvarh is not None
            else None,
        )

    def guardar_instantanea(self, lectura: LecturaInstantanea) -> None:
        model = TelemetryInstantaneousModel(
            device_id=lectura.dispositivo_id,
            recorded_at=lectura.registrado_en,
            voltage_r=lectura.fase_r.tension.voltios if lectura.fase_r.tension else None,
            current_r=lectura.fase_r.corriente.amperios if lectura.fase_r.corriente else None,
            active_power_r=lectura.fase_r.potencia_activa.vatios if lectura.fase_r.potencia_activa else None,
            reactive_power_r=lectura.fase_r.potencia_reactiva.var if lectura.fase_r.potencia_reactiva else None,
            apparent_power_r=lectura.fase_r.potencia_aparente.va if lectura.fase_r.potencia_aparente else None,
            power_factor_r=lectura.fase_r.factor_potencia.valor if lectura.fase_r.factor_potencia else None,
            thd_v_r=Decimal(str(lectura.fase_r.thd_v_porcentaje))
            if lectura.fase_r.thd_v_porcentaje is not None
            else None,
            thd_i_r=Decimal(str(lectura.fase_r.thd_i_porcentaje))
            if lectura.fase_r.thd_i_porcentaje is not None
            else None,
            voltage_s=lectura.fase_s.tension.voltios if lectura.fase_s.tension else None,
            current_s=lectura.fase_s.corriente.amperios if lectura.fase_s.corriente else None,
            active_power_s=lectura.fase_s.potencia_activa.vatios if lectura.fase_s.potencia_activa else None,
            reactive_power_s=lectura.fase_s.potencia_reactiva.var if lectura.fase_s.potencia_reactiva else None,
            apparent_power_s=lectura.fase_s.potencia_aparente.va if lectura.fase_s.potencia_aparente else None,
            power_factor_s=lectura.fase_s.factor_potencia.valor if lectura.fase_s.factor_potencia else None,
            thd_v_s=Decimal(str(lectura.fase_s.thd_v_porcentaje))
            if lectura.fase_s.thd_v_porcentaje is not None
            else None,
            thd_i_s=Decimal(str(lectura.fase_s.thd_i_porcentaje))
            if lectura.fase_s.thd_i_porcentaje is not None
            else None,
            voltage_t=lectura.fase_t.tension.voltios if lectura.fase_t.tension else None,
            current_t=lectura.fase_t.corriente.amperios if lectura.fase_t.corriente else None,
            active_power_t=lectura.fase_t.potencia_activa.vatios if lectura.fase_t.potencia_activa else None,
            reactive_power_t=lectura.fase_t.potencia_reactiva.var if lectura.fase_t.potencia_reactiva else None,
            apparent_power_t=lectura.fase_t.potencia_aparente.va if lectura.fase_t.potencia_aparente else None,
            power_factor_t=lectura.fase_t.factor_potencia.valor if lectura.fase_t.factor_potencia else None,
            thd_v_t=Decimal(str(lectura.fase_t.thd_v_porcentaje))
            if lectura.fase_t.thd_v_porcentaje is not None
            else None,
            thd_i_t=Decimal(str(lectura.fase_t.thd_i_porcentaje))
            if lectura.fase_t.thd_i_porcentaje is not None
            else None,
            total_active_power=lectura.potencia_activa_total.vatios if lectura.potencia_activa_total else None,
            total_reactive_power=lectura.potencia_reactiva_total.var if lectura.potencia_reactiva_total else None,
            total_apparent_power=lectura.potencia_aparente_total.va if lectura.potencia_aparente_total else None,
            total_power_factor=lectura.factor_potencia_total.valor if lectura.factor_potencia_total else None,
            desbalance_tension_porcentaje=lectura.desbalance_tension_porcentaje,
            current_n=lectura.corriente_neutro_estimada.amperios if lectura.corriente_neutro_estimada else None,
            voltage_linea_V=lectura.voltage_linea_V,
            tension_neutro_estimada=lectura.tension_neutro_estimada,
            thd_v_promedio_porcentaje=Decimal(str(lectura.thd_v_promedio_porcentaje))
            if lectura.thd_v_promedio_porcentaje is not None
            else None,
            thd_i_total_porcentaje=Decimal(str(lectura.thd_i_total_porcentaje))
            if lectura.thd_i_total_porcentaje is not None
            else None,
        )
        self.db.add(model)
        self.db.commit()

    def guardar_energia(self, acumulado: AcumuladoEnergia) -> None:
        model = TelemetryEnergyModel(
            device_id=acumulado.dispositivo_id,
            recorded_at=acumulado.registrado_en,
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
        self.db.add(model)
        self.db.commit()

    def guardar_log_estado(self, log: LogEstadoDispositivo) -> None:
        model = DeviceStatusLogModel(
            device_id=log.dispositivo_id,
            recorded_at=log.registrado_en,
            wifi_rssi_dbm=log.wifi_rssi_dbm,
            wifi_calidad=log.wifi_calidad,
            ip_address=log.direccion_ip,
            uptime_seconds=log.tiempo_activo_segundos,
            raw_payload=log.payload_bruto,
        )
        self.db.add(model)
        self.db.commit()

    def _alerta_to_entity(self, m: DeviceAlertModel) -> AlertaDispositivo:
        return AlertaDispositivo(
            id=m.id,
            dispositivo_id=m.device_id,
            tipo_alerta=m.alert_type,
            severidad=SeveridadAlerta(m.severity)
            if m.severity in SeveridadAlerta._value2member_map_
            else SeveridadAlerta.WARNING,
            mensaje=m.message,
            esta_resuelta=m.is_resolved,
            disparada_en=m.triggered_at,
            resuelta_en=m.resolved_at,
            fase=m.phase,
            valor_medido=float(m.measured_value) if m.measured_value is not None else None,
            valor_umbral=float(m.threshold_value) if m.threshold_value is not None else None,
            unidad=m.unit,
            categoria=m.category,
            observaciones=m.notes,
        )

    def guardar_alerta(self, alerta: AlertaDispositivo) -> None:
        if alerta.id is not None:
            model = self.db.query(DeviceAlertModel).filter(DeviceAlertModel.id == alerta.id).first()
            if model:
                model.device_id = alerta.dispositivo_id
                model.alert_type = alerta.tipo_alerta
                model.severity = alerta.severidad.value
                model.message = alerta.mensaje
                model.is_resolved = alerta.esta_resuelta
                model.triggered_at = alerta.disparada_en
                model.resolved_at = alerta.resuelta_en
                model.phase = alerta.fase
                model.measured_value = Decimal(str(alerta.valor_medido)) if alerta.valor_medido is not None else None
                model.threshold_value = Decimal(str(alerta.valor_umbral)) if alerta.valor_umbral is not None else None
                model.unit = alerta.unidad
                model.category = alerta.categoria
                model.notes = alerta.observaciones
                self.db.commit()
                return

        model = DeviceAlertModel(
            device_id=alerta.dispositivo_id,
            alert_type=alerta.tipo_alerta,
            severity=alerta.severidad.value,
            message=alerta.mensaje,
            is_resolved=alerta.esta_resuelta,
            triggered_at=alerta.disparada_en,
            resolved_at=alerta.resuelta_en,
            phase=alerta.fase,
            measured_value=Decimal(str(alerta.valor_medido)) if alerta.valor_medido is not None else None,
            threshold_value=Decimal(str(alerta.valor_umbral)) if alerta.valor_umbral is not None else None,
            unit=alerta.unidad,
            category=alerta.categoria,
            notes=alerta.observaciones,
        )
        self.db.add(model)
        self.db.commit()
        if alerta.id is None:
            alerta.id = model.id

    def listar_alertas(
        self,
        dispositivo_id: str | None = None,
        solo_abiertas: bool = False,
        severidad: str | None = None,
        limite: int = 100,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> list[AlertaDispositivo]:
        q = self.db.query(DeviceAlertModel)
        if dispositivo_id:
            q = q.filter(DeviceAlertModel.device_id == dispositivo_id)
        if solo_abiertas:
            q = q.filter(DeviceAlertModel.is_resolved.is_(False))
        if severidad:
            q = q.filter(DeviceAlertModel.severity == severidad.upper())
        if desde:
            q = q.filter(DeviceAlertModel.triggered_at >= desde)
        if hasta:
            q = q.filter(DeviceAlertModel.triggered_at <= hasta)
        items = q.order_by(desc(DeviceAlertModel.triggered_at)).limit(limite).all()
        return [self._alerta_to_entity(m) for m in items]

    def obtener_alerta_por_id(self, alerta_id: int) -> AlertaDispositivo | None:
        m = self.db.query(DeviceAlertModel).filter(DeviceAlertModel.id == alerta_id).first()
        return self._alerta_to_entity(m) if m else None

    def obtener_ultima_instantanea(self, dispositivo_id: str) -> LecturaInstantanea | None:
        m = (
            self.db.query(TelemetryInstantaneousModel)
            .filter(TelemetryInstantaneousModel.device_id == dispositivo_id)
            .order_by(desc(TelemetryInstantaneousModel.recorded_at))
            .first()
        )
        return self._instantanea_to_entity(m) if m else None

    def obtener_ultimo_acumulado(self, dispositivo_id: str) -> AcumuladoEnergia | None:
        m = (
            self.db.query(TelemetryEnergyModel)
            .filter(TelemetryEnergyModel.device_id == dispositivo_id)
            .order_by(desc(TelemetryEnergyModel.recorded_at))
            .first()
        )
        return self._energia_to_entity(m) if m else None

    def listar_instantaneas(
        self, dispositivo_id: str, limite: int, desde: datetime | None = None
    ) -> list[LecturaInstantanea]:
        q = self.db.query(TelemetryInstantaneousModel).filter(TelemetryInstantaneousModel.device_id == dispositivo_id)
        if desde:
            q = q.filter(TelemetryInstantaneousModel.recorded_at >= desde)
        items = q.order_by(desc(TelemetryInstantaneousModel.recorded_at)).limit(limite).all()
        return [self._instantanea_to_entity(m) for m in items]

    def listar_energias(
        self, dispositivo_id: str, limite: int, desde: datetime | None = None
    ) -> list[AcumuladoEnergia]:
        q = self.db.query(TelemetryEnergyModel).filter(TelemetryEnergyModel.device_id == dispositivo_id)
        if desde:
            q = q.filter(TelemetryEnergyModel.recorded_at >= desde)
        items = q.order_by(desc(TelemetryEnergyModel.recorded_at)).limit(limite).all()
        return [self._energia_to_entity(m) for m in items]

    def listar_acumulados_para_agregacion(
        self, dispositivo_id: str, desde: datetime | None = None
    ) -> list[AcumuladoEnergia]:
        q = self.db.query(TelemetryEnergyModel).filter(TelemetryEnergyModel.device_id == dispositivo_id)
        if desde:
            q = q.filter(TelemetryEnergyModel.recorded_at >= desde)
        items = q.order_by(asc(TelemetryEnergyModel.recorded_at)).all()
        return [self._energia_to_entity(m) for m in items]

    def listar_potencias_para_histograma(
        self, dispositivo_id: str, desde: datetime, limite: int | None = None
    ) -> list[LecturaPotenciaTemporal]:
        q = (
            self.db.query(
                TelemetryInstantaneousModel.recorded_at,
                TelemetryInstantaneousModel.total_active_power,
            )
            .filter(
                TelemetryInstantaneousModel.device_id == dispositivo_id,
                TelemetryInstantaneousModel.recorded_at >= desde,
                TelemetryInstantaneousModel.total_active_power.isnot(None),
            )
            .order_by(asc(TelemetryInstantaneousModel.recorded_at))
        )
        if limite is not None:
            q = q.limit(limite)
        filas = q.all()
        return [LecturaPotenciaTemporal(momento=fila[0], potencia_w=float(fila[1])) for fila in filas]

    def purgar_instantaneas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        ids = [
            row[0]
            for row in self.db.query(TelemetryInstantaneousModel.id)
            .filter(TelemetryInstantaneousModel.recorded_at < fecha_limite)
            .limit(batch_size)
            .all()
        ]
        if not ids:
            return 0
        deleted = (
            self.db.query(TelemetryInstantaneousModel)
            .filter(TelemetryInstantaneousModel.id.in_(ids))
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted

    def purgar_energias_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        ids = [
            row[0]
            for row in self.db.query(TelemetryEnergyModel.id)
            .filter(TelemetryEnergyModel.recorded_at < fecha_limite)
            .limit(batch_size)
            .all()
        ]
        if not ids:
            return 0
        deleted = (
            self.db.query(TelemetryEnergyModel)
            .filter(TelemetryEnergyModel.id.in_(ids))
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted

    def purgar_status_logs_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        ids = [
            row[0]
            for row in self.db.query(DeviceStatusLogModel.id)
            .filter(DeviceStatusLogModel.recorded_at < fecha_limite)
            .limit(batch_size)
            .all()
        ]
        if not ids:
            return 0
        deleted = (
            self.db.query(DeviceStatusLogModel)
            .filter(DeviceStatusLogModel.id.in_(ids))
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted

    def purgar_alertas_resueltas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        ids = [
            row[0]
            for row in self.db.query(DeviceAlertModel.id)
            .filter(DeviceAlertModel.is_resolved.is_(True), DeviceAlertModel.resolved_at < fecha_limite)
            .limit(batch_size)
            .all()
        ]
        if not ids:
            return 0
        deleted = self.db.query(DeviceAlertModel).filter(DeviceAlertModel.id.in_(ids)).delete(synchronize_session=False)
        self.db.commit()
        return deleted

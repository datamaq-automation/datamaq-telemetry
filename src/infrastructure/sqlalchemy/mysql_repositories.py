from datetime import datetime
from decimal import Decimal

from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.ports import RepositorioUsuariosPort
from src.domain.telemetria.entities import (
    AcumuladoEnergia,
    AlertaDispositivo,
    Dispositivo,
    LecturaInstantanea,
    LogEstadoDispositivo,
    MedicionFase,
    Organizacion,
    Planta,
    PlanTelemetria,
)
from src.domain.telemetria.ports import (
    RepositorioDispositivosPort,
    RepositorioOrganizacionesPort,
    RepositorioPlanesPort,
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.services import AnalizadorCalidadEnergiaService
from src.domain.telemetria.value_objects import (
    Corriente,
    EnergiaActiva,
    EnergiaReactiva,
    EstadoDispositivo,
    FactorPotencia,
    MacAddress,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    SeveridadAlerta,
    Tension,
    VisibilidadPlan,
)
from src.infrastructure.sqlalchemy.models import (
    DeviceAlertModel,
    DeviceModel,
    DeviceStatusLogModel,
    FacilityModel,
    OrganizationModel,
    PlanModel,
    TelemetryEnergyModel,
    TelemetryInstantaneousModel,
    UserModel,
)


class MySQLDispositivosRepository(RepositorioDispositivosPort):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: DeviceModel) -> Dispositivo:
        return Dispositivo(
            id=model.id,
            device_uid=MacAddress(model.device_uid),
            nombre=model.name,
            modelo=model.model,
            planta_id=model.facility_id,
            numero_serie=model.serial_number,
            version_hw=model.hw_version,
            version_fw=model.fw_version,
            ubicacion_tag=model.tag_location,
            esta_activo=model.esta_activo,
            estado=EstadoDispositivo(model.estado)
            if model.estado in EstadoDispositivo._value2member_map_
            else EstadoDispositivo.OFFLINE,
            visto_por_ultima_vez=model.last_seen_at,
            tipo_instalacion=getattr(model, "installation_type", "CONSUMO") or "CONSUMO",
            fases_con_ti=getattr(model, "phases_with_ct", "R,S,T") or "R,S,T",
            creado_en=model.created_at,
            actualizado_en=model.updated_at,
        )

    def obtener_por_id(self, dispositivo_id: str) -> Dispositivo | None:
        model = self.db.query(DeviceModel).filter(DeviceModel.id == dispositivo_id).first()
        return self._to_entity(model) if model else None

    def obtener_por_uid(self, uid: MacAddress) -> Dispositivo | None:
        model = self.db.query(DeviceModel).filter(DeviceModel.device_uid == uid.valor).first()
        return self._to_entity(model) if model else None

    def listar(self, planta_id: str | None = None) -> list[Dispositivo]:
        query = self.db.query(DeviceModel)
        if planta_id:
            query = query.filter(DeviceModel.facility_id == planta_id)
        return [self._to_entity(m) for m in query.all()]

    def contar_por_organizacion(self, organizacion_id: str) -> int:
        return (
            self.db.query(DeviceModel)
            .join(FacilityModel, DeviceModel.facility_id == FacilityModel.id)
            .filter(FacilityModel.organization_id == organizacion_id)
            .count()
        )

    def guardar(self, dispositivo: Dispositivo) -> Dispositivo:
        model = self.db.query(DeviceModel).filter(DeviceModel.id == dispositivo.id).first()
        if not model:
            model = DeviceModel(
                id=dispositivo.id,
                facility_id=dispositivo.planta_id,
                device_uid=dispositivo.device_uid.valor,
                serial_number=dispositivo.numero_serie,
                name=dispositivo.nombre,
                model=dispositivo.modelo,
                hw_version=dispositivo.version_hw,
                fw_version=dispositivo.version_fw,
                tag_location=dispositivo.ubicacion_tag,
                esta_activo=dispositivo.esta_activo,
                estado=dispositivo.estado.value,
                last_seen_at=dispositivo.visto_por_ultima_vez,
                installation_type=dispositivo.tipo_instalacion,
                phases_with_ct=dispositivo.fases_con_ti,
            )
            self.db.add(model)
        else:
            model.name = dispositivo.nombre
            model.facility_id = dispositivo.planta_id
            model.model = dispositivo.modelo
            model.serial_number = dispositivo.numero_serie
            model.hw_version = dispositivo.version_hw
            model.fw_version = dispositivo.version_fw
            model.tag_location = dispositivo.ubicacion_tag
            model.esta_activo = dispositivo.esta_activo
            model.estado = dispositivo.estado.value
            model.last_seen_at = dispositivo.visto_por_ultima_vez
            model.installation_type = dispositivo.tipo_instalacion
            model.phases_with_ct = dispositivo.fases_con_ti

        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)


class MySQLTelemetriaRepository(RepositorioTelemetriaPort):
    def __init__(self, db: Session):
        self.db = db

    def _to_fase(self, v, i, p, q, s, fp) -> MedicionFase:
        return MedicionFase(
            tension=Tension(voltios=float(v)) if v is not None else None,
            corriente=Corriente(amperios=float(i)) if i is not None else None,
            potencia_activa=PotenciaActiva(vatios=float(p)) if p is not None else None,
            potencia_reactiva=PotenciaReactiva(var=float(q)) if q is not None else None,
            potencia_aparente=PotenciaAparente(va=float(s)) if s is not None else None,
            factor_potencia=FactorPotencia(valor=float(fp)) if fp is not None else None,
        )

    def _instantanea_to_entity(self, m: TelemetryInstantaneousModel) -> LecturaInstantanea:
        fase_r = self._to_fase(
            m.voltage_r, m.current_r, m.active_power_r, m.reactive_power_r, m.apparent_power_r, m.power_factor_r
        )
        fase_s = self._to_fase(
            m.voltage_s, m.current_s, m.active_power_s, m.reactive_power_s, m.apparent_power_s, m.power_factor_s
        )
        fase_t = self._to_fase(
            m.voltage_t, m.current_t, m.active_power_t, m.reactive_power_t, m.apparent_power_t, m.power_factor_t
        )

        in_obj = None
        if hasattr(m, "current_n") and m.current_n is not None:
            in_obj = Corriente(amperios=float(m.current_n))
        else:
            in_obj = AnalizadorCalidadEnergiaService.calcular_corriente_neutro(
                ir=fase_r.corriente.amperios if fase_r.corriente else None,
                is_=fase_s.corriente.amperios if fase_s.corriente else None,
                it=fase_t.corriente.amperios if fase_t.corriente else None,
                pr=fase_r.potencia_activa.vatios if fase_r.potencia_activa else None,
                ps=fase_s.potencia_activa.vatios if fase_s.potencia_activa else None,
                pt=fase_t.potencia_activa.vatios if fase_t.potencia_activa else None,
                qr=fase_r.potencia_reactiva.var if fase_r.potencia_reactiva else None,
                qs=fase_s.potencia_reactiva.var if fase_s.potencia_reactiva else None,
                qt=fase_t.potencia_reactiva.var if fase_t.potencia_reactiva else None,
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
            voltage_s=lectura.fase_s.tension.voltios if lectura.fase_s.tension else None,
            current_s=lectura.fase_s.corriente.amperios if lectura.fase_s.corriente else None,
            active_power_s=lectura.fase_s.potencia_activa.vatios if lectura.fase_s.potencia_activa else None,
            reactive_power_s=lectura.fase_s.potencia_reactiva.var if lectura.fase_s.potencia_reactiva else None,
            apparent_power_s=lectura.fase_s.potencia_aparente.va if lectura.fase_s.potencia_aparente else None,
            power_factor_s=lectura.fase_s.factor_potencia.valor if lectura.fase_s.factor_potencia else None,
            voltage_t=lectura.fase_t.tension.voltios if lectura.fase_t.tension else None,
            current_t=lectura.fase_t.corriente.amperios if lectura.fase_t.corriente else None,
            active_power_t=lectura.fase_t.potencia_activa.vatios if lectura.fase_t.potencia_activa else None,
            reactive_power_t=lectura.fase_t.potencia_reactiva.var if lectura.fase_t.potencia_reactiva else None,
            apparent_power_t=lectura.fase_t.potencia_aparente.va if lectura.fase_t.potencia_aparente else None,
            power_factor_t=lectura.fase_t.factor_potencia.valor if lectura.fase_t.factor_potencia else None,
            total_active_power=lectura.potencia_activa_total.vatios if lectura.potencia_activa_total else None,
            total_reactive_power=lectura.potencia_reactiva_total.var if lectura.potencia_reactiva_total else None,
            total_apparent_power=lectura.potencia_aparente_total.va if lectura.potencia_aparente_total else None,
            total_power_factor=lectura.factor_potencia_total.valor if lectura.factor_potencia_total else None,
            desbalance_tension_porcentaje=lectura.desbalance_tension_porcentaje,
            current_n=lectura.corriente_neutro_estimada.amperios if lectura.corriente_neutro_estimada else None,
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
        )
        self.db.add(model)
        self.db.commit()
        if alerta.id is None:
            alerta.id = model.id

    def listar_alertas(
        self,
        dispositivo_id: str | None = None,
        solo_abiertas: bool = False,
        limite: int = 100,
    ) -> list[AlertaDispositivo]:
        q = self.db.query(DeviceAlertModel)
        if dispositivo_id:
            q = q.filter(DeviceAlertModel.device_id == dispositivo_id)
        if solo_abiertas:
            q = q.filter(DeviceAlertModel.is_resolved.is_(False))
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


class MySQLOrganizacionesRepository(RepositorioOrganizacionesPort):
    def __init__(self, db: Session):
        self.db = db

    def obtener_por_id(self, organizacion_id: str) -> Organizacion | None:
        m = self.db.query(OrganizationModel).filter(OrganizationModel.id == organizacion_id).first()
        if not m:
            return None
        return Organizacion(
            id=m.id,
            nombre=m.name,
            plan_id=m.plan_id,
            cuit=m.tax_id,
            email_contacto=m.contact_email,
            telefono_contacto=m.contact_phone,
            creado_en=m.created_at,
            actualizado_en=m.updated_at,
        )

    def listar_organizaciones(self) -> list[Organizacion]:
        models = self.db.query(OrganizationModel).all()
        return [
            Organizacion(
                id=m.id,
                nombre=m.name,
                plan_id=m.plan_id,
                cuit=m.tax_id,
                email_contacto=m.contact_email,
                telefono_contacto=m.contact_phone,
                creado_en=m.created_at,
                actualizado_en=m.updated_at,
            )
            for m in models
        ]

    def guardar_organizacion(self, org: Organizacion) -> Organizacion:
        model = self.db.query(OrganizationModel).filter(OrganizationModel.id == org.id).first()
        if not model:
            model = OrganizationModel(
                id=org.id,
                name=org.nombre,
                plan_id=org.plan_id,
                tax_id=org.cuit,
                contact_email=org.email_contacto,
                contact_phone=org.telefono_contacto,
            )
            self.db.add(model)
        else:
            model.name = org.nombre
            model.plan_id = org.plan_id
            model.tax_id = org.cuit
            model.contact_email = org.email_contacto
            model.contact_phone = org.telefono_contacto

        self.db.commit()
        self.db.refresh(model)
        return Organizacion(
            id=model.id,
            nombre=model.name,
            plan_id=model.plan_id,
            cuit=model.tax_id,
            email_contacto=model.contact_email,
            telefono_contacto=model.contact_phone,
            creado_en=model.created_at,
            actualizado_en=model.updated_at,
        )

    def obtener_planta_por_id(self, planta_id: str) -> Planta | None:
        m = self.db.query(FacilityModel).filter(FacilityModel.id == planta_id).first()
        if not m:
            return None
        return Planta(
            id=m.id,
            organizacion_id=m.organization_id,
            nombre=m.name,
            direccion=m.address,
            latitud=float(m.latitude) if m.latitude is not None else None,
            longitud=float(m.longitude) if m.longitude is not None else None,
            creado_en=m.created_at,
            actualizado_en=m.updated_at,
        )

    def listar_plantas(self, organizacion_id: str | None = None) -> list[Planta]:
        q = self.db.query(FacilityModel)
        if organizacion_id:
            q = q.filter(FacilityModel.organization_id == organizacion_id)
        return [
            Planta(
                id=m.id,
                organizacion_id=m.organization_id,
                nombre=m.name,
                direccion=m.address,
                latitud=float(m.latitude) if m.latitude is not None else None,
                longitud=float(m.longitude) if m.longitude is not None else None,
                creado_en=m.created_at,
                actualizado_en=m.updated_at,
            )
            for m in q.all()
        ]

    def guardar_planta(self, planta: Planta) -> Planta:
        model = self.db.query(FacilityModel).filter(FacilityModel.id == planta.id).first()
        lat_dec = Decimal(str(planta.latitud)) if planta.latitud is not None else None
        lon_dec = Decimal(str(planta.longitud)) if planta.longitud is not None else None
        if not model:
            model = FacilityModel(
                id=planta.id,
                organization_id=planta.organizacion_id,
                name=planta.nombre,
                address=planta.direccion,
                latitude=lat_dec,
                longitude=lon_dec,
            )
            self.db.add(model)
        else:
            model.organization_id = planta.organizacion_id
            model.name = planta.nombre
            model.address = planta.direccion
            model.latitude = lat_dec
            model.longitude = lon_dec

        self.db.commit()
        self.db.refresh(model)
        return Planta(
            id=model.id,
            organizacion_id=model.organization_id,
            nombre=model.name,
            direccion=model.address,
            latitud=float(model.latitude) if model.latitude is not None else None,
            longitud=float(model.longitude) if model.longitude is not None else None,
            creado_en=model.created_at,
            actualizado_en=model.updated_at,
        )


class MySQLPlanesRepository(RepositorioPlanesPort):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: PlanModel) -> PlanTelemetria:
        return PlanTelemetria(
            id=model.id,
            nombre=model.name,
            descripcion=model.description,
            precio_mensual_ars=Decimal(str(model.monthly_price_ars)),
            visibilidad=VisibilidadPlan(model.visibility)
            if model.visibility in VisibilidadPlan._value2member_map_
            else VisibilidadPlan.PUBLICO,
            retencion_dias=model.retention_days,
            granularidad_minutos=model.granularity_minutes,
            max_dispositivos=model.max_devices,
            canales_notificacion=list(model.notification_channels or []),
            creado_en=model.created_at,
            actualizado_en=model.updated_at,
        )

    def listar_planes(self) -> list[PlanTelemetria]:
        models = self.db.query(PlanModel).all()
        return [self._to_entity(m) for m in models]

    def obtener_por_id(self, plan_id: str) -> PlanTelemetria | None:
        model = self.db.query(PlanModel).filter(PlanModel.id == plan_id).first()
        if not model:
            return None
        return self._to_entity(model)

    def guardar_plan(self, plan: PlanTelemetria) -> PlanTelemetria:
        model = self.db.query(PlanModel).filter(PlanModel.id == plan.id).first()
        if not model:
            model = PlanModel(
                id=plan.id,
                name=plan.nombre,
                description=plan.descripcion,
                monthly_price_ars=plan.precio_mensual_ars,
                visibility=plan.visibilidad.value,
                retention_days=plan.retencion_dias,
                granularity_minutes=plan.granularidad_minutos,
                max_devices=plan.max_dispositivos,
                notification_channels=plan.canales_notificacion,
            )
            self.db.add(model)
        else:
            model.name = plan.nombre
            model.description = plan.descripcion
            model.monthly_price_ars = plan.precio_mensual_ars
            model.visibility = plan.visibilidad.value
            model.retention_days = plan.retencion_dias
            model.granularity_minutes = plan.granularidad_minutos
            model.max_devices = plan.max_dispositivos
            model.notification_channels = plan.canales_notificacion

        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)


class MySQLUsuariosRepository(RepositorioUsuariosPort):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: UserModel) -> UsuarioAuth:
        return UsuarioAuth(
            id=model.id,
            usuario=model.username,
            hash_contrasena=model.password_hash,
            esta_activo=model.is_active,
            rol=model.role,
            creado_en=model.created_at,
            actualizado_en=model.updated_at,
        )

    def obtener_por_usuario(self, usuario: str) -> UsuarioAuth | None:
        model = self.db.query(UserModel).filter(UserModel.username == usuario).first()
        return self._to_entity(model) if model else None

    def guardar(self, usuario: UsuarioAuth) -> UsuarioAuth:
        model = self.db.query(UserModel).filter(UserModel.id == usuario.id).first()
        if not model:
            model = UserModel(
                id=usuario.id,
                username=usuario.usuario,
                password_hash=usuario.hash_contrasena,
                role=usuario.rol,
                is_active=usuario.esta_activo,
            )
            self.db.add(model)
        else:
            model.username = usuario.usuario
            model.password_hash = usuario.hash_contrasena
            model.role = usuario.rol
            model.is_active = usuario.esta_activo

        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

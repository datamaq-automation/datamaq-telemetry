from sqlalchemy.orm import Session

from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.ports import RepositorioDispositivosPort
from src.domain.telemetria.value_objects import EstadoDispositivo, MacAddress
from src.infrastructure.sqlalchemy.models import DeviceModel, FacilityModel


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

    def listar(self, planta_id: str | None = None, organizacion_id: str | None = None) -> list[Dispositivo]:
        query = self.db.query(DeviceModel)
        if organizacion_id:
            query = query.join(FacilityModel, DeviceModel.facility_id == FacilityModel.id).filter(
                FacilityModel.organization_id == organizacion_id
            )
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

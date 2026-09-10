from datetime import datetime
from decimal import Decimal

from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from src.domain.disponibilidad.entities import EventoDisponibilidad, Maquina, ParadaProgramada
from src.domain.disponibilidad.ports import (
    RepositorioEventosDisponibilidadPort,
    RepositorioMaquinasPort,
    RepositorioParadasProgramadasPort,
)
from src.domain.disponibilidad.value_objects import EstadoMaquina, OrigenClasificacion, TipoParada
from src.infrastructure.sqlalchemy.models import (
    DeviceModel,
    FacilityModel,
    MachineAvailabilityEventModel,
    MachineModel,
    ScheduledStopModel,
)


class MySQLMaquinasRepository(RepositorioMaquinasPort):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: MachineModel) -> Maquina:
        return Maquina(
            id=model.id,
            dispositivo_id=model.device_id,
            nombre=model.name,
            umbral_marcha_w=float(model.on_threshold_w) if model.on_threshold_w is not None else None,
            ventana_persistencia_lecturas=model.persistence_readings,
            ventana_persistencia_segundos=float(model.persistence_seconds),
            creado_en=model.created_at,
            actualizado_en=model.updated_at,
        )

    def obtener_por_id(self, maquina_id: str) -> Maquina | None:
        model = self.db.query(MachineModel).filter(MachineModel.id == maquina_id).first()
        return self._to_entity(model) if model else None

    def obtener_por_dispositivo_id(self, dispositivo_id: str) -> Maquina | None:
        model = self.db.query(MachineModel).filter(MachineModel.device_id == dispositivo_id).first()
        return self._to_entity(model) if model else None

    def listar(self, organizacion_id: str | None = None) -> list[Maquina]:
        query = self.db.query(MachineModel)
        if organizacion_id:
            query = (
                query.join(DeviceModel, MachineModel.device_id == DeviceModel.id)
                .join(FacilityModel, DeviceModel.facility_id == FacilityModel.id)
                .filter(FacilityModel.organization_id == organizacion_id)
            )
        return [self._to_entity(m) for m in query.all()]

    def guardar(self, maquina: Maquina) -> Maquina:
        model = self.db.query(MachineModel).filter(MachineModel.id == maquina.id).first()
        if not model:
            model = MachineModel(
                id=maquina.id,
                device_id=maquina.dispositivo_id,
                name=maquina.nombre,
                on_threshold_w=Decimal(str(maquina.umbral_marcha_w)) if maquina.umbral_marcha_w is not None else None,
                persistence_readings=maquina.ventana_persistencia_lecturas,
                persistence_seconds=Decimal(str(maquina.ventana_persistencia_segundos)),
            )
            self.db.add(model)
        else:
            model.name = maquina.nombre
            model.on_threshold_w = (
                Decimal(str(maquina.umbral_marcha_w)) if maquina.umbral_marcha_w is not None else None
            )
            model.persistence_readings = maquina.ventana_persistencia_lecturas
            model.persistence_seconds = Decimal(str(maquina.ventana_persistencia_segundos))

        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)


class MySQLEventosDisponibilidadRepository(RepositorioEventosDisponibilidadPort):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: MachineAvailabilityEventModel) -> EventoDisponibilidad:
        return EventoDisponibilidad(
            id=model.id,
            maquina_id=model.machine_id,
            estado=EstadoMaquina(model.state),
            inicio_at=model.start_at,
            fin_at=model.end_at,
            tipo_parada=TipoParada(model.stop_type) if model.stop_type else None,
            potencia_promedio_w=float(model.avg_power_w) if model.avg_power_w is not None else None,
            origen=OrigenClasificacion(model.origin),
            corregido_por_usuario_id=model.corrected_by_user_id,
            corregido_at=model.corrected_at,
            comentario=model.notes,
        )

    def obtener_por_id(self, evento_id: int) -> EventoDisponibilidad | None:
        model = (
            self.db.query(MachineAvailabilityEventModel).filter(MachineAvailabilityEventModel.id == evento_id).first()
        )
        return self._to_entity(model) if model else None

    def obtener_evento_abierto(self, maquina_id: str) -> EventoDisponibilidad | None:
        model = (
            self.db.query(MachineAvailabilityEventModel)
            .filter(
                MachineAvailabilityEventModel.machine_id == maquina_id,
                MachineAvailabilityEventModel.end_at.is_(None),
            )
            .order_by(desc(MachineAvailabilityEventModel.start_at))
            .first()
        )
        return self._to_entity(model) if model else None

    def listar_por_maquina(self, maquina_id: str, limite: int = 100) -> list[EventoDisponibilidad]:
        modelos = (
            self.db.query(MachineAvailabilityEventModel)
            .filter(MachineAvailabilityEventModel.machine_id == maquina_id)
            .order_by(desc(MachineAvailabilityEventModel.start_at))
            .limit(limite)
            .all()
        )
        return [self._to_entity(m) for m in modelos]

    def listar_por_rango(self, maquina_id: str, desde: datetime, hasta: datetime) -> list[EventoDisponibilidad]:
        modelos = (
            self.db.query(MachineAvailabilityEventModel)
            .filter(
                MachineAvailabilityEventModel.machine_id == maquina_id,
                MachineAvailabilityEventModel.start_at <= hasta,
                or_(
                    MachineAvailabilityEventModel.end_at.is_(None),
                    MachineAvailabilityEventModel.end_at >= desde,
                ),
            )
            .order_by(MachineAvailabilityEventModel.start_at.asc())
            .all()
        )
        return [self._to_entity(m) for m in modelos]

    def guardar(self, evento: EventoDisponibilidad) -> EventoDisponibilidad:
        model = (
            self.db.query(MachineAvailabilityEventModel).filter(MachineAvailabilityEventModel.id == evento.id).first()
            if evento.id is not None
            else None
        )
        if not model:
            model = MachineAvailabilityEventModel(
                machine_id=evento.maquina_id,
                state=evento.estado.value,
                stop_type=evento.tipo_parada.value if evento.tipo_parada else None,
                start_at=evento.inicio_at,
                end_at=evento.fin_at,
                avg_power_w=Decimal(str(evento.potencia_promedio_w))
                if evento.potencia_promedio_w is not None
                else None,
                origin=evento.origen.value,
                corrected_by_user_id=evento.corregido_por_usuario_id,
                corrected_at=evento.corregido_at,
                notes=evento.comentario,
            )
            self.db.add(model)
        else:
            model.state = evento.estado.value
            model.stop_type = evento.tipo_parada.value if evento.tipo_parada else None
            model.end_at = evento.fin_at
            model.avg_power_w = (
                Decimal(str(evento.potencia_promedio_w)) if evento.potencia_promedio_w is not None else None
            )
            model.origin = evento.origen.value
            model.corrected_by_user_id = evento.corregido_por_usuario_id
            model.corrected_at = evento.corregido_at
            model.notes = evento.comentario

        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)


class MySQLParadasProgramadasRepository(RepositorioParadasProgramadasPort):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: ScheduledStopModel) -> ParadaProgramada:
        return ParadaProgramada(
            id=model.id,
            maquina_id=model.machine_id,
            inicio_at=model.start_at,
            fin_at=model.end_at,
            motivo=model.reason,
            creado_por_usuario_id=model.created_by_user_id,
            creado_en=model.created_at,
        )

    def guardar(self, parada: ParadaProgramada) -> ParadaProgramada:
        model = ScheduledStopModel(
            id=parada.id,
            machine_id=parada.maquina_id,
            start_at=parada.inicio_at,
            end_at=parada.fin_at,
            reason=parada.motivo,
            created_by_user_id=parada.creado_por_usuario_id,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def listar_por_maquina(self, maquina_id: str) -> list[ParadaProgramada]:
        modelos = (
            self.db.query(ScheduledStopModel)
            .filter(ScheduledStopModel.machine_id == maquina_id)
            .order_by(desc(ScheduledStopModel.start_at))
            .all()
        )
        return [self._to_entity(m) for m in modelos]

    def buscar_vigente(self, maquina_id: str, instante: datetime) -> ParadaProgramada | None:
        model = (
            self.db.query(ScheduledStopModel)
            .filter(
                ScheduledStopModel.machine_id == maquina_id,
                ScheduledStopModel.start_at <= instante,
                ScheduledStopModel.end_at >= instante,
            )
            .first()
        )
        return self._to_entity(model) if model else None

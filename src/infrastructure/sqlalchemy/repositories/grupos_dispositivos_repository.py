"""src/infrastructure/sqlalchemy/repositories/grupos_dispositivos_repository.py."""

from sqlalchemy.orm import Session

from src.domain.telemetria.entities import Dispositivo, GrupoDispositivos
from src.domain.telemetria.ports import RepositorioGruposDispositivosPort
from src.infrastructure.sqlalchemy.models import DeviceGroupMemberModel, DeviceGroupModel
from src.infrastructure.sqlalchemy.repositories.dispositivos_repository import MySQLDispositivosRepository


class MySQLGruposDispositivosRepository(RepositorioGruposDispositivosPort):
    def __init__(self, db: Session):
        self.db = db
        self._repo_dispositivos = MySQLDispositivosRepository(db)

    def _to_entity(self, model: DeviceGroupModel) -> GrupoDispositivos:
        return GrupoDispositivos(
            id=model.id,
            planta_id=model.facility_id,
            nombre=model.name,
            dispositivos_ids=[m.device_id for m in model.members],
            creado_en=model.created_at,
            actualizado_en=model.updated_at,
        )

    def crear(self, grupo: GrupoDispositivos) -> GrupoDispositivos:
        model = DeviceGroupModel(id=grupo.id, facility_id=grupo.planta_id, name=grupo.nombre)
        self.db.add(model)
        self.db.flush()
        for dispositivo_id in grupo.dispositivos_ids:
            self.db.add(DeviceGroupMemberModel(group_id=grupo.id, device_id=dispositivo_id))
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def obtener_por_id(self, grupo_id: str) -> GrupoDispositivos | None:
        model = self.db.query(DeviceGroupModel).filter(DeviceGroupModel.id == grupo_id).first()
        return self._to_entity(model) if model else None

    def listar_por_planta(self, planta_id: str) -> list[GrupoDispositivos]:
        models = self.db.query(DeviceGroupModel).filter(DeviceGroupModel.facility_id == planta_id).all()
        return [self._to_entity(m) for m in models]

    def agregar_miembro(self, grupo_id: str, dispositivo_id: str) -> None:
        existente = (
            self.db.query(DeviceGroupMemberModel)
            .filter(
                DeviceGroupMemberModel.group_id == grupo_id,
                DeviceGroupMemberModel.device_id == dispositivo_id,
            )
            .first()
        )
        if existente is None:
            self.db.add(DeviceGroupMemberModel(group_id=grupo_id, device_id=dispositivo_id))
            self.db.commit()

    def quitar_miembro(self, grupo_id: str, dispositivo_id: str) -> None:
        self.db.query(DeviceGroupMemberModel).filter(
            DeviceGroupMemberModel.group_id == grupo_id,
            DeviceGroupMemberModel.device_id == dispositivo_id,
        ).delete()
        self.db.commit()

    def eliminar(self, grupo_id: str) -> None:
        self.db.query(DeviceGroupModel).filter(DeviceGroupModel.id == grupo_id).delete()
        self.db.commit()

    def listar_dispositivos_miembro(self, grupo_id: str) -> list[Dispositivo]:
        model = self.db.query(DeviceGroupModel).filter(DeviceGroupModel.id == grupo_id).first()
        if model is None:
            return []
        dispositivos = []
        for miembro in model.members:
            dispositivo = self._repo_dispositivos.obtener_por_id(miembro.device_id)
            if dispositivo is not None:
                dispositivos.append(dispositivo)
        return dispositivos

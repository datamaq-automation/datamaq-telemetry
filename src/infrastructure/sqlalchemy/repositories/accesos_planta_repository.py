"""src/infrastructure/sqlalchemy/repositories/accesos_planta_repository.py."""

from sqlalchemy.orm import Session

from src.domain.auth.entities import AccesoPlantaUsuario
from src.domain.auth.ports import RepositorioAccesosPlantaPort
from src.infrastructure.sqlalchemy.models import UserFacilityAccessModel


class MySQLAccesosPlantaRepository(RepositorioAccesosPlantaPort):
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _to_entity(model: UserFacilityAccessModel) -> AccesoPlantaUsuario:
        return AccesoPlantaUsuario(
            usuario_id=model.user_id,
            planta_id=model.facility_id,
            puede_cambiar=model.can_switch,
            creado_en=model.created_at,
        )

    def listar_por_usuario(self, usuario_id: str) -> list[AccesoPlantaUsuario]:
        modelos = (
            self.db.query(UserFacilityAccessModel)
            .filter(UserFacilityAccessModel.user_id == usuario_id)
            .order_by(UserFacilityAccessModel.created_at, UserFacilityAccessModel.facility_id)
            .all()
        )
        return [self._to_entity(m) for m in modelos]

    def reemplazar(self, usuario_id: str, accesos: list[AccesoPlantaUsuario]) -> list[AccesoPlantaUsuario]:
        self.db.query(UserFacilityAccessModel).filter(UserFacilityAccessModel.user_id == usuario_id).delete()
        for acceso in accesos:
            self.db.add(
                UserFacilityAccessModel(
                    user_id=usuario_id,
                    facility_id=acceso.planta_id,
                    can_switch=acceso.puede_cambiar,
                    created_at=acceso.creado_en,
                )
            )
        self.db.commit()
        return self.listar_por_usuario(usuario_id)

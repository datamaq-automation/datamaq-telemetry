"""src/infrastructure/sqlalchemy/repositories/dispositivos_confiables_repository.py."""
from datetime import datetime

from sqlalchemy.orm import Session

from src.domain.auth.entities import DispositivoConfiable
from src.domain.auth.ports import RepositorioDispositivosConfiablesPort
from src.infrastructure.sqlalchemy.models import DispositivoConfiableModel


class MySQLDispositivosConfiablesRepository(RepositorioDispositivosConfiablesPort):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: DispositivoConfiableModel) -> DispositivoConfiable:
        return DispositivoConfiable(
            id=model.id,
            usuario_id=model.usuario_id,
            token_hash=model.token_hash,
            nombre_dispositivo=model.nombre_dispositivo,
            user_agent=model.user_agent,
            ip_origen=model.ip_origen,
            creado_en=model.creado_en,
            ultimo_acceso_en=model.ultimo_acceso_en,
            expira_en=model.expira_en,
            revocado=model.revocado,
        )

    def obtener_por_hash(self, token_hash: str) -> DispositivoConfiable | None:
        model = (
            self.db.query(DispositivoConfiableModel).filter(DispositivoConfiableModel.token_hash == token_hash).first()
        )
        return self._to_entity(model) if model else None

    def guardar(self, dispositivo: DispositivoConfiable) -> DispositivoConfiable:
        model = self.db.query(DispositivoConfiableModel).filter(DispositivoConfiableModel.id == dispositivo.id).first()
        if not model:
            model = DispositivoConfiableModel(
                id=dispositivo.id,
                usuario_id=dispositivo.usuario_id,
                token_hash=dispositivo.token_hash,
                nombre_dispositivo=dispositivo.nombre_dispositivo,
                user_agent=dispositivo.user_agent,
                ip_origen=dispositivo.ip_origen,
                creado_en=dispositivo.creado_en,
                ultimo_acceso_en=dispositivo.ultimo_acceso_en,
                expira_en=dispositivo.expira_en,
                revocado=dispositivo.revocado,
            )
            self.db.add(model)
        else:
            model.token_hash = dispositivo.token_hash
            model.nombre_dispositivo = dispositivo.nombre_dispositivo
            model.user_agent = dispositivo.user_agent
            model.ip_origen = dispositivo.ip_origen
            model.ultimo_acceso_en = dispositivo.ultimo_acceso_en
            model.expira_en = dispositivo.expira_en
            model.revocado = dispositivo.revocado

        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def actualizar_acceso(self, id: str, ip: str, ultimo_acceso: datetime) -> None:
        model = self.db.query(DispositivoConfiableModel).filter(DispositivoConfiableModel.id == id).first()
        if model:
            model.ip_origen = ip
            model.ultimo_acceso_en = ultimo_acceso
            self.db.commit()

    def revocar_todos_de_usuario(self, usuario_id: str) -> int:
        modelos = (
            self.db.query(DispositivoConfiableModel)
            .filter(
                DispositivoConfiableModel.usuario_id == usuario_id,
                DispositivoConfiableModel.revocado.is_(False),
            )
            .all()
        )
        for model in modelos:
            model.revocado = True
        self.db.commit()
        return len(modelos)

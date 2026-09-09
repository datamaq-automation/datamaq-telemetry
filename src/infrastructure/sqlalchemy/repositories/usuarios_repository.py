from sqlalchemy.orm import Session

from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.ports import RepositorioUsuariosPort
from src.infrastructure.sqlalchemy.models import UserModel


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
            organizacion_id=model.organization_id,
            totp_secret=model.totp_secret,
            totp_enabled=model.totp_enabled,
            totp_backup_codes=model.totp_backup_codes,
            creado_en=model.created_at,
            actualizado_en=model.updated_at,
        )

    def obtener_por_usuario(self, usuario: str) -> UsuarioAuth | None:
        model = self.db.query(UserModel).filter(UserModel.username == usuario).first()
        return self._to_entity(model) if model else None

    def obtener_por_id(self, usuario_id: str) -> UsuarioAuth | None:
        model = self.db.query(UserModel).filter(UserModel.id == usuario_id).first()
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
                organization_id=usuario.organizacion_id,
                totp_secret=usuario.totp_secret,
                totp_enabled=usuario.totp_enabled,
                totp_backup_codes=usuario.totp_backup_codes,
            )
            self.db.add(model)
        else:
            model.username = usuario.usuario
            model.password_hash = usuario.hash_contrasena
            model.role = usuario.rol
            model.is_active = usuario.esta_activo
            model.organization_id = usuario.organizacion_id
            model.totp_secret = usuario.totp_secret
            model.totp_enabled = usuario.totp_enabled
            model.totp_backup_codes = usuario.totp_backup_codes

        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

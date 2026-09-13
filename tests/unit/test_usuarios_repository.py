"""tests/unit/test_usuarios_repository.py — Suite de tests unitarios para MySQLUsuariosRepository."""

from collections.abc import Iterator
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.domain.auth.entities import UsuarioAuth
from src.infrastructure.sqlalchemy.models import Base, OrganizationModel, UserModel
from src.infrastructure.sqlalchemy.repositories.usuarios_repository import (
    MySQLUsuariosRepository,
)


@pytest.fixture()
def mock_db() -> MagicMock:
    """Fixture que provee un Mock estricto de Session de SQLAlchemy."""
    return MagicMock(spec=Session)


@pytest.fixture()
def usuario_auth_fixture() -> UsuarioAuth:
    """Instancia de prueba para la entidad de dominio UsuarioAuth."""
    now = datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)
    return UsuarioAuth(
        id="usr-100",
        usuario="operador_planta",
        hash_contrasena="hash_seguro_123",
        esta_activo=True,
        rol="operador",
        organizacion_id="org-50",
        totp_secret="JBSWY3DPEHPK3PXP",
        totp_enabled=True,
        totp_backup_codes=["code1", "code2"],
        creado_en=now,
        actualizado_en=now,
    )


class TestMySQLUsuariosRepositoryMocks:
    """Tests unitarios usando Mocks de Session de SQLAlchemy."""

    def test_init_asigna_sesion(self, mock_db: MagicMock):
        repo = MySQLUsuariosRepository(mock_db)
        assert repo.db is mock_db

    def test_to_entity_mapeo_completo(self, mock_db: MagicMock):
        repo = MySQLUsuariosRepository(mock_db)
        ahora = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)

        model = UserModel(
            id="usr-01",
            username="admin_user",
            password_hash="pbkdf2:sha256:fakehash",
            role="admin",
            is_active=True,
            organization_id="org-01",
            totp_secret="SECRET123",
            totp_enabled=True,
            totp_backup_codes=["abc", "xyz"],
        )
        model.created_at = ahora
        model.updated_at = ahora

        entity = repo._to_entity(model)

        assert entity.id == "usr-01"
        assert entity.usuario == "admin_user"
        assert entity.hash_contrasena == "pbkdf2:sha256:fakehash"
        assert entity.rol == "admin"
        assert entity.esta_activo is True
        assert entity.organizacion_id == "org-01"
        assert entity.totp_secret == "SECRET123"
        assert entity.totp_enabled is True
        assert entity.totp_backup_codes == ["abc", "xyz"]
        assert entity.creado_en == ahora
        assert entity.actualizado_en == ahora

    def test_obtener_por_usuario_existente(self, mock_db: MagicMock):
        repo = MySQLUsuariosRepository(mock_db)
        now = datetime(2026, 9, 12, 8, 0, 0, tzinfo=timezone.utc)

        mock_model = UserModel(
            id="usr-10",
            username="juan_perez",
            password_hash="hashed_pw_abc",
            role="supervisor",
            is_active=True,
            organization_id="org-10",
            totp_secret=None,
            totp_enabled=False,
            totp_backup_codes=None,
        )
        mock_model.created_at = now
        mock_model.updated_at = now

        mock_db.query.return_value.filter.return_value.first.return_value = mock_model

        resultado = repo.obtener_por_usuario("juan_perez")

        mock_db.query.assert_called_once_with(UserModel)
        mock_db.query.return_value.filter.assert_called_once()
        mock_db.query.return_value.filter.return_value.first.assert_called_once()

        assert resultado is not None
        assert resultado.id == "usr-10"
        assert resultado.usuario == "juan_perez"
        assert resultado.rol == "supervisor"
        assert resultado.hash_contrasena == "hashed_pw_abc"
        assert resultado.organizacion_id == "org-10"
        assert resultado.creado_en == now
        assert resultado.actualizado_en == now

    def test_obtener_por_usuario_inexistente(self, mock_db: MagicMock):
        repo = MySQLUsuariosRepository(mock_db)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        resultado = repo.obtener_por_usuario("usuario_fantasma")

        mock_db.query.assert_called_once_with(UserModel)
        assert resultado is None

    def test_obtener_por_id_existente(self, mock_db: MagicMock):
        repo = MySQLUsuariosRepository(mock_db)
        now = datetime(2026, 9, 12, 9, 0, 0, tzinfo=timezone.utc)

        mock_model = UserModel(
            id="usr-20",
            username="maria_lopez",
            password_hash="hashed_pw_xyz",
            role="operador",
            is_active=True,
            organization_id="org-20",
            totp_secret="SECRET",
            totp_enabled=True,
            totp_backup_codes=["bk1"],
        )
        mock_model.created_at = now
        mock_model.updated_at = now

        mock_db.query.return_value.filter.return_value.first.return_value = mock_model

        resultado = repo.obtener_por_id("usr-20")

        mock_db.query.assert_called_once_with(UserModel)
        assert resultado is not None
        assert resultado.id == "usr-20"
        assert resultado.usuario == "maria_lopez"
        assert resultado.totp_enabled is True
        assert resultado.totp_backup_codes == ["bk1"]

    def test_obtener_por_id_inexistente(self, mock_db: MagicMock):
        repo = MySQLUsuariosRepository(mock_db)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        resultado = repo.obtener_por_id("usr-no-existe")

        mock_db.query.assert_called_once_with(UserModel)
        assert resultado is None

    def test_guardar_nuevo_usuario(self, mock_db: MagicMock, usuario_auth_fixture: UsuarioAuth):
        repo = MySQLUsuariosRepository(mock_db)
        # El usuario no existe previamente en la base de datos
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Simulamos que al hacer refresh, el modelo mantiene los timestamps
        def _simulate_refresh(model: UserModel):
            model.created_at = usuario_auth_fixture.creado_en
            model.updated_at = usuario_auth_fixture.actualizado_en

        mock_db.refresh.side_effect = _simulate_refresh

        resultado = repo.guardar(usuario_auth_fixture)

        mock_db.query.assert_called_once_with(UserModel)
        mock_db.add.assert_called_once()
        added_model = mock_db.add.call_args[0][0]

        assert isinstance(added_model, UserModel)
        assert added_model.id == usuario_auth_fixture.id
        assert added_model.username == usuario_auth_fixture.usuario
        assert added_model.password_hash == usuario_auth_fixture.hash_contrasena
        assert added_model.role == usuario_auth_fixture.rol
        assert added_model.is_active == usuario_auth_fixture.esta_activo
        assert added_model.organization_id == usuario_auth_fixture.organizacion_id
        assert added_model.totp_secret == usuario_auth_fixture.totp_secret
        assert added_model.totp_enabled == usuario_auth_fixture.totp_enabled
        assert added_model.totp_backup_codes == usuario_auth_fixture.totp_backup_codes

        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(added_model)

        assert resultado.id == usuario_auth_fixture.id
        assert resultado.usuario == usuario_auth_fixture.usuario
        assert resultado.hash_contrasena == usuario_auth_fixture.hash_contrasena
        assert resultado.rol == usuario_auth_fixture.rol
        assert resultado.organizacion_id == usuario_auth_fixture.organizacion_id

    def test_guardar_actualizar_usuario_existente(self, mock_db: MagicMock, usuario_auth_fixture: UsuarioAuth):
        repo = MySQLUsuariosRepository(mock_db)

        # Modelo preexistente en la base de datos con valores anteriores
        existing_model = UserModel(
            id=usuario_auth_fixture.id,
            username="antiguo_usuario",
            password_hash="antiguo_hash",
            role="visitante",
            is_active=False,
            organization_id="antigua_org",
            totp_secret=None,
            totp_enabled=False,
            totp_backup_codes=None,
        )
        existing_model.created_at = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        existing_model.updated_at = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        mock_db.query.return_value.filter.return_value.first.return_value = existing_model

        resultado = repo.guardar(usuario_auth_fixture)

        mock_db.query.assert_called_once_with(UserModel)
        # No se debe llamar a add puesto que ya existe en la sesión
        mock_db.add.assert_not_called()

        # Verificamos que se hayan actualizado todos los campos del modelo existente
        assert existing_model.username == usuario_auth_fixture.usuario
        assert existing_model.password_hash == usuario_auth_fixture.hash_contrasena
        assert existing_model.role == usuario_auth_fixture.rol
        assert existing_model.is_active == usuario_auth_fixture.esta_activo
        assert existing_model.organization_id == usuario_auth_fixture.organizacion_id
        assert existing_model.totp_secret == usuario_auth_fixture.totp_secret
        assert existing_model.totp_enabled == usuario_auth_fixture.totp_enabled
        assert existing_model.totp_backup_codes == usuario_auth_fixture.totp_backup_codes

        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(existing_model)

        assert resultado.usuario == usuario_auth_fixture.usuario
        assert resultado.hash_contrasena == usuario_auth_fixture.hash_contrasena
        assert resultado.rol == usuario_auth_fixture.rol
        assert resultado.esta_activo is True


@pytest.fixture()
def sqlite_session() -> Iterator[Session]:
    """Sesión SQLite en memoria para tests de integración reales con SQLAlchemy."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    org = OrganizationModel(id="org-sql-1")
    session.add(org)
    session.commit()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class TestMySQLUsuariosRepositorySQLite:
    """Tests de integración con SQLite en memoria para validar queries y restricciones reales."""

    def test_guardar_nuevo_y_obtener_por_id(self, sqlite_session: Session, usuario_auth_fixture: UsuarioAuth):
        usuario_auth_fixture.organizacion_id = "org-sql-1"
        repo = MySQLUsuariosRepository(sqlite_session)

        guardado = repo.guardar(usuario_auth_fixture)
        assert guardado.id == usuario_auth_fixture.id

        recuperado = repo.obtener_por_id(usuario_auth_fixture.id)
        assert recuperado is not None
        assert recuperado.id == usuario_auth_fixture.id
        assert recuperado.usuario == usuario_auth_fixture.usuario
        assert recuperado.hash_contrasena == usuario_auth_fixture.hash_contrasena
        assert recuperado.rol == usuario_auth_fixture.rol
        assert recuperado.organizacion_id == "org-sql-1"
        assert recuperado.totp_enabled is True
        assert recuperado.totp_backup_codes == ["code1", "code2"]

    def test_obtener_por_usuario(self, sqlite_session: Session, usuario_auth_fixture: UsuarioAuth):
        usuario_auth_fixture.organizacion_id = "org-sql-1"
        repo = MySQLUsuariosRepository(sqlite_session)
        repo.guardar(usuario_auth_fixture)

        encontrado = repo.obtener_por_usuario(usuario_auth_fixture.usuario)
        assert encontrado is not None
        assert encontrado.id == usuario_auth_fixture.id
        assert encontrado.usuario == usuario_auth_fixture.usuario

        no_encontrado = repo.obtener_por_usuario("usuario_inexistente")
        assert no_encontrado is None

    def test_actualizar_usuario_existente(self, sqlite_session: Session, usuario_auth_fixture: UsuarioAuth):
        usuario_auth_fixture.organizacion_id = "org-sql-1"
        repo = MySQLUsuariosRepository(sqlite_session)
        repo.guardar(usuario_auth_fixture)

        # Modificamos los datos del usuario
        usuario_modificado = UsuarioAuth(
            id=usuario_auth_fixture.id,
            usuario="operador_modificado",
            hash_contrasena="nuevo_hash_seguro",
            esta_activo=False,
            rol="admin",
            organizacion_id="org-sql-1",
            totp_secret=None,
            totp_enabled=False,
            totp_backup_codes=None,
        )
        actualizado = repo.guardar(usuario_modificado)

        assert actualizado.usuario == "operador_modificado"
        assert actualizado.hash_contrasena == "nuevo_hash_seguro"
        assert actualizado.esta_activo is False
        assert actualizado.rol == "admin"
        assert actualizado.totp_enabled is False
        assert actualizado.totp_backup_codes is None

        # Consultamos nuevamente de la base de datos
        db_user = repo.obtener_por_id(usuario_auth_fixture.id)
        assert db_user is not None
        assert db_user.usuario == "operador_modificado"
        assert db_user.hash_contrasena == "nuevo_hash_seguro"
        assert db_user.esta_activo is False
        assert db_user.rol == "admin"

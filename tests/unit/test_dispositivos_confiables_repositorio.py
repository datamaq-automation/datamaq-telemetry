"""tests/unit/test_dispositivos_confiables_repositorio.py — Repositorio SQLAlchemy de dispositivos confiables, con SQLite en memoria."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.domain.auth.entities import DispositivoConfiable, ahora_utc
from src.infrastructure.sqlalchemy.models import Base, UserModel
from src.infrastructure.sqlalchemy.repositories.dispositivos_confiables_repository import (
    MySQLDispositivosConfiablesRepository,
)

USUARIO_ID = "user-1"
OTRO_USUARIO_ID = "user-2"


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(UserModel(id=USUARIO_ID, username="operador1", password_hash="hash"))
    session.add(UserModel(id=OTRO_USUARIO_ID, username="operador2", password_hash="hash"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _dispositivo(**overrides) -> DispositivoConfiable:
    ahora = ahora_utc()
    base = dict(
        id="disp-1",
        usuario_id=USUARIO_ID,
        token_hash="hash-token-1",
        nombre_dispositivo="Chrome en notebook",
        user_agent="Mozilla/5.0",
        ip_origen="192.168.1.10",
        creado_en=ahora,
        ultimo_acceso_en=ahora,
        expira_en=ahora + timedelta(days=30),
        revocado=False,
    )
    base.update(overrides)
    return DispositivoConfiable(**base)


class TestMySQLDispositivosConfiablesRepository:
    def test_guardar_crea_dispositivo_nuevo(self, db: Session):
        repo = MySQLDispositivosConfiablesRepository(db)

        creado = repo.guardar(_dispositivo())

        assert creado.id == "disp-1"
        assert creado.usuario_id == USUARIO_ID
        assert creado.token_hash == "hash-token-1"
        assert creado.revocado is False

    def test_guardar_actualiza_dispositivo_existente(self, db: Session):
        repo = MySQLDispositivosConfiablesRepository(db)
        repo.guardar(_dispositivo())

        actualizado = repo.guardar(_dispositivo(nombre_dispositivo="Firefox en desktop", ip_origen="10.0.0.5"))

        assert actualizado.nombre_dispositivo == "Firefox en desktop"
        assert actualizado.ip_origen == "10.0.0.5"

    def test_obtener_por_hash_encuentra_dispositivo(self, db: Session):
        repo = MySQLDispositivosConfiablesRepository(db)
        repo.guardar(_dispositivo())

        encontrado = repo.obtener_por_hash("hash-token-1")

        assert encontrado is not None
        assert encontrado.id == "disp-1"

    def test_obtener_por_hash_inexistente_devuelve_none(self, db: Session):
        repo = MySQLDispositivosConfiablesRepository(db)
        assert repo.obtener_por_hash("no-existe") is None

    def test_actualizar_acceso_modifica_ip_y_fecha(self, db: Session):
        repo = MySQLDispositivosConfiablesRepository(db)
        repo.guardar(_dispositivo())
        nuevo_acceso = ahora_utc()

        repo.actualizar_acceso("disp-1", "172.16.0.1", nuevo_acceso)

        actualizado = repo.obtener_por_hash("hash-token-1")
        assert actualizado.ip_origen == "172.16.0.1"
        assert actualizado.ultimo_acceso_en == nuevo_acceso

    def test_actualizar_acceso_de_dispositivo_inexistente_no_falla(self, db: Session):
        repo = MySQLDispositivosConfiablesRepository(db)
        repo.actualizar_acceso("no-existe", "172.16.0.1", ahora_utc())

    def test_revocar_todos_de_usuario_marca_solo_los_de_ese_usuario(self, db: Session):
        repo = MySQLDispositivosConfiablesRepository(db)
        repo.guardar(_dispositivo(id="disp-1", token_hash="hash-1", usuario_id=USUARIO_ID))
        repo.guardar(_dispositivo(id="disp-2", token_hash="hash-2", usuario_id=USUARIO_ID))
        repo.guardar(_dispositivo(id="disp-3", token_hash="hash-3", usuario_id=OTRO_USUARIO_ID))

        cantidad = repo.revocar_todos_de_usuario(USUARIO_ID)

        assert cantidad == 2
        assert repo.obtener_por_hash("hash-1").revocado is True
        assert repo.obtener_por_hash("hash-2").revocado is True
        assert repo.obtener_por_hash("hash-3").revocado is False

    def test_revocar_todos_de_usuario_no_recuenta_ya_revocados(self, db: Session):
        repo = MySQLDispositivosConfiablesRepository(db)
        repo.guardar(_dispositivo(id="disp-1", token_hash="hash-1", revocado=True))

        cantidad = repo.revocar_todos_de_usuario(USUARIO_ID)

        assert cantidad == 0

    def test_revocar_todos_de_usuario_sin_dispositivos_devuelve_cero(self, db: Session):
        repo = MySQLDispositivosConfiablesRepository(db)
        assert repo.revocar_todos_de_usuario("no-existe") == 0

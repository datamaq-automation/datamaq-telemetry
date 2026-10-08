"""Repositorio SQLAlchemy de cambio de contraseña sobre SQLite en memoria."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.infrastructure.sqlalchemy.models import (
    AuditoriaChangeContraseniaModel,
    Base,
    CambioContraseniaValidacionModel,
    UserModel,
)
from src.infrastructure.sqlalchemy.repositories.cambio_contrasena_repository import (
    MySQLCambioContrasenaRepository,
)

AHORA = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(UserModel(id="u-1", username="operador@example.com", password_hash="x", role="operador"))
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def repo(db: Session) -> MySQLCambioContrasenaRepository:
    return MySQLCambioContrasenaRepository(db)


def test_crear_guarda_hash_y_no_el_codigo(repo, db):
    repo.crear_validacion("u-1", "a" * 64, AHORA + timedelta(minutes=10), AHORA)
    fila = db.query(CambioContraseniaValidacionModel).one()
    assert fila.codigo_hash == "a" * 64
    assert fila.intentos_fallidos == 0


def test_obtener_vigente_devuelve_la_mas_reciente_y_no_expirada(repo):
    repo.crear_validacion("u-1", "a" * 64, AHORA + timedelta(minutes=10), AHORA - timedelta(minutes=5))
    nueva = repo.crear_validacion("u-1", "b" * 64, AHORA + timedelta(minutes=10), AHORA)
    vigente = repo.obtener_vigente("u-1", AHORA)
    assert vigente is not None and vigente.id == nueva.id


def test_obtener_vigente_ignora_expiradas_y_consumidas(repo):
    expirada = repo.crear_validacion("u-1", "a" * 64, AHORA - timedelta(seconds=1), AHORA - timedelta(minutes=11))
    assert repo.obtener_vigente("u-1", AHORA) is None
    consumida = repo.crear_validacion("u-1", "b" * 64, AHORA + timedelta(minutes=10), AHORA)
    repo.consumir(consumida.id, AHORA)
    assert repo.obtener_vigente("u-1", AHORA) is None
    assert expirada.id != consumida.id


def test_invalidar_vigentes_consume_solo_las_del_usuario(repo):
    repo.crear_validacion("u-1", "a" * 64, AHORA + timedelta(minutes=10), AHORA)
    otra = repo.crear_validacion("u-2", "b" * 64, AHORA + timedelta(minutes=10), AHORA)
    repo.invalidar_vigentes("u-1", AHORA)
    assert repo.obtener_vigente("u-1", AHORA) is None
    assert repo.obtener_vigente("u-2", AHORA).id == otra.id


def test_contar_solicitudes_respeta_la_ventana(repo):
    repo.crear_validacion("u-1", "a" * 64, AHORA, AHORA - timedelta(minutes=11))
    repo.crear_validacion("u-1", "b" * 64, AHORA, AHORA - timedelta(minutes=2))
    repo.crear_validacion("u-1", "c" * 64, AHORA, AHORA - timedelta(minutes=1))
    assert repo.contar_solicitudes_desde("u-1", AHORA - timedelta(minutes=10)) == 2


def test_registrar_intento_fallido_incrementa_y_devuelve_total(repo):
    v = repo.crear_validacion("u-1", "a" * 64, AHORA + timedelta(minutes=10), AHORA)
    assert repo.registrar_intento_fallido(v.id) == 1
    assert repo.registrar_intento_fallido(v.id) == 2


def test_registrar_intento_sobre_validacion_inexistente_falla(repo):
    with pytest.raises(ValueError):
        repo.registrar_intento_fallido(9999)


def test_auditoria_guarda_estado_ip_y_trunca_user_agent(repo, db):
    repo.registrar_auditoria("u-1", "intento_fallido", "10.0.0.1", "x" * 300, AHORA)
    fila = db.query(AuditoriaChangeContraseniaModel).one()
    assert fila.estado == "intento_fallido"
    assert fila.ip == "10.0.0.1"
    assert len(fila.user_agent) == 255


def test_contar_auditoria_filtra_por_usuario_estado_y_ventana(repo):
    repo.registrar_auditoria("u-1", "intento_fallido", "10.0.0.1", None, AHORA)
    repo.registrar_auditoria("u-1", "intento_fallido", "10.0.0.1", None, AHORA - timedelta(minutes=11))
    repo.registrar_auditoria("u-1", "cambio_exitoso", "10.0.0.1", None, AHORA)
    repo.registrar_auditoria("u-2", "intento_fallido", "10.0.0.1", None, AHORA)
    assert repo.contar_auditoria_desde("u-1", "intento_fallido", AHORA - timedelta(minutes=10)) == 1

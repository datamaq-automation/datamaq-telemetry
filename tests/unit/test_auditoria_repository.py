"""tests/unit/test_auditoria_repository.py — Tests del repositorio de auditoría con SQLite en memoria."""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.domain.auditoria.entities import RegistroAuditoria
from src.infrastructure.sqlalchemy.models import Base
from src.infrastructure.sqlalchemy.repositories.auditoria_repository import MySQLAuditoriaRepository


@pytest.fixture()
def db_session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def test_registrar_y_listar_auditoria(db_session: Session):
    repo = MySQLAuditoriaRepository(db_session)
    ahora = datetime.now(timezone.utc)

    evento1 = RegistroAuditoria(
        id="evt-1",
        registrado_en=ahora - timedelta(minutes=5),
        categoria="AUTH",
        accion="LOGIN_EXITOSO",
        resultado="EXITO",
        actor_usuario_id="user-1",
        actor_email="user1@planta.local",
        actor_ip="192.168.1.10",
        actor_user_agent="Mozilla/5.0",
        recurso_tipo="usuario",
        recurso_id="user-1",
        metadatos={"metodo": "totp"},
    )
    evento2 = RegistroAuditoria(
        id="evt-2",
        registrado_en=ahora,
        categoria="METROLOGIA",
        accion="CALIBRACION_ACTUALIZADA",
        resultado="EXITO",
        actor_usuario_id="user-1",
        recurso_tipo="dispositivo",
        recurso_id="dev-100",
        metadatos={"tipo_instalacion": {"anterior": "monofasica", "nuevo": "trifasica"}},
    )

    repo.registrar(evento1)
    repo.registrar(evento2)

    # Listar todos
    todos = repo.listar()
    assert len(todos) == 2
    # Orden cronológico descendente (el más reciente primero)
    assert todos[0].id == "evt-2"
    assert todos[1].id == "evt-1"

    # Filtrar por categoría
    auth_logs = repo.listar(categoria="AUTH")
    assert len(auth_logs) == 1
    assert auth_logs[0].id == "evt-1"

    # Filtrar por recurso
    dev_logs = repo.listar(recurso_tipo="dispositivo", recurso_id="dev-100")
    assert len(dev_logs) == 1
    assert dev_logs[0].id == "evt-2"

    # Contar
    assert repo.contar() == 2
    assert repo.contar(categoria="METROLOGIA") == 1
    assert repo.contar(categoria="SISTEMA") == 0


def test_paginacion_auditoria(db_session: Session):
    repo = MySQLAuditoriaRepository(db_session)
    ahora = datetime.now(timezone.utc)

    for i in range(10):
        repo.registrar(
            RegistroAuditoria(
                id=f"evt-{i}",
                registrado_en=ahora - timedelta(minutes=i),
                categoria="AUTH",
                accion="LOGIN_EXITOSO",
                resultado="EXITO",
            )
        )

    pagina1 = repo.listar(limite=5, offset=0)
    pagina2 = repo.listar(limite=5, offset=5)

    assert len(pagina1) == 5
    assert len(pagina2) == 5
    assert pagina1[0].id != pagina2[0].id
    assert repo.contar() == 10

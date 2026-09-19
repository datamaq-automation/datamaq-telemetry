# tests/unit/test_asistente_repository.py
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.domain.asistente.entities import MensajeAsistente, RegistroClasificacionIntencion
from src.infrastructure.sqlalchemy.models import Base
from src.infrastructure.sqlalchemy.repositories.asistente_repository import (
    MySQLConversacionesAsistenteRepository,
)


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_asistente_repository_crear_y_obtener(db: Session):
    repo = MySQLConversacionesAsistenteRepository(db)

    conv = repo.crear_conversacion(organizacion_id="org-1", usuario_id="user-1")
    assert conv.id is not None
    assert conv.organizacion_id == "org-1"
    assert conv.usuario_id == "user-1"

    conv_db = repo.obtener_conversacion(conv.id, organizacion_id="org-1")
    assert conv_db is not None
    assert conv_db.id == conv.id

    conv_otra_org = repo.obtener_conversacion(conv.id, organizacion_id="org-2")
    assert conv_otra_org is None


def test_asistente_repository_mensajes(db: Session):
    repo = MySQLConversacionesAsistenteRepository(db)
    conv = repo.crear_conversacion(organizacion_id="org-1", usuario_id="user-1")

    msg_user = MensajeAsistente(
        id="msg-1",
        conversacion_id=conv.id,
        rol="usuario",
        texto="Hola asistente",
    )
    msg_asst = MensajeAsistente(
        id="msg-2",
        conversacion_id=conv.id,
        rol="asistente",
        texto="Hola, ¿en qué puedo ayudarte?",
    )

    repo.guardar_mensaje(msg_user, organizacion_id="org-1")
    repo.guardar_mensaje(msg_asst, organizacion_id="org-1")

    mensajes = repo.listar_mensajes(conv.id, organizacion_id="org-1")
    assert len(mensajes) == 2
    assert mensajes[0].texto == "Hola asistente"
    assert mensajes[1].texto == "Hola, ¿en qué puedo ayudarte?"

    # Intentar listar mensajes con otra organizacion_id
    mensajes_org2 = repo.listar_mensajes(conv.id, organizacion_id="org-2")
    assert len(mensajes_org2) == 0


def test_asistente_repository_clasificacion(db: Session):
    from src.domain.asistente.entities import IntencionClasificada

    repo = MySQLConversacionesAsistenteRepository(db)
    conv = repo.crear_conversacion(organizacion_id="org-1", usuario_id="user-1")

    msg_user = MensajeAsistente(
        id="msg-1",
        conversacion_id=conv.id,
        rol="usuario",
        texto="¿Cuánto consumí hoy?",
    )
    repo.guardar_mensaje(msg_user, organizacion_id="org-1")

    reg = RegistroClasificacionIntencion(
        id="reg-1",
        mensaje_id="msg-1",
        intencion=IntencionClasificada(nombre="CONSULTA_CONSUMO", confianza=0.95),
    )
    repo.guardar_clasificacion(reg, organizacion_id="org-1")

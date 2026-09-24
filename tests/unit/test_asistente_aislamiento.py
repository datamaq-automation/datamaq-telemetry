"""tests/unit/test_asistente_aislamiento.py — El asistente no ve medidores ni alertas de otra organización (OWASP A01).

Repositorios SQLAlchemy reales sobre SQLite en memoria: org A (planta, medidor y alerta) y org B (ídem).
"""

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.application.use_cases.asistente.procesar_pregunta_asistente import ProcesarPreguntaAsistenteUseCase
from src.application.use_cases.gestionar_alertas import GestionarAlertasUseCase
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.infrastructure.asistente.clasificador_reglas import ClasificadorIntencionReglasAdapter
from src.infrastructure.fastapi.dependencies import get_procesar_pregunta_asistente_use_case, get_usuario_actual
from src.infrastructure.fastapi.routes.asistente_router import router as asistente_router
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.sqlalchemy.models import (
    Base,
    DeviceAlertModel,
    DeviceModel,
    FacilityModel,
    OrganizationModel,
)
from src.infrastructure.sqlalchemy.repositories.dispositivos_repository import MySQLDispositivosRepository
from src.infrastructure.sqlalchemy.repositories.telemetria_repository import MySQLTelemetriaRepository


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for n, org in enumerate(("org-a", "org-b"), start=1):
        letra = org[-1]
        session.add(OrganizationModel(id=org))
        session.add(FacilityModel(id=f"planta-{letra}", organization_id=org, name=f"Planta {letra}"))
        session.add(
            DeviceModel(
                id=f"dev-{letra}",
                facility_id=f"planta-{letra}",
                device_uid=f"AABBCCDDEE0{n}",
                name=f"Medidor {letra.upper()}",
            )
        )
        session.add(
            DeviceAlertModel(
                id=n,
                device_id=f"dev-{letra}",
                alert_type=f"ALERTA_ORG_{letra.upper()}",
                severity="WARNING",
                message="x",
            )
        )
    session.commit()
    try:
        yield session
    finally:
        session.close()


class GeneradorQueCaptura:
    def __init__(self) -> None:
        self.contextos: list[str] = []

    def generar(self, pregunta: str, contexto: str) -> Iterator[str]:
        self.contextos.append(contexto)
        yield "ok"


def _use_case(db: Session, generador: GeneradorQueCaptura) -> ProcesarPreguntaAsistenteUseCase:
    repo_org = MagicMock()
    repo_org.obtener_dispositivos_layout.return_value = []
    repo_conv = MagicMock()
    repo_conv.crear_conversacion.return_value = MagicMock(id="conv-1")
    return ProcesarPreguntaAsistenteUseCase(
        clasificador=ClasificadorIntencionReglasAdapter(),
        generador=generador,
        repo_conversaciones=repo_conv,
        gestor_alertas=GestionarAlertasUseCase(MySQLTelemetriaRepository(db)),
        gestor_dispositivos=GestionarDispositivosUseCase(MySQLDispositivosRepository(db), repo_org),
    )


def test_repositorio_de_alertas_filtra_por_organizacion(db: Session):
    repo = MySQLTelemetriaRepository(db)
    assert [a.tipo_alerta for a in repo.listar_alertas(organizacion_id="org-a")] == ["ALERTA_ORG_A"]
    assert {a.tipo_alerta for a in repo.listar_alertas()} == {"ALERTA_ORG_A", "ALERTA_ORG_B"}


def test_contexto_del_asistente_solo_tiene_datos_de_la_organizacion_del_usuario(db: Session):
    generador = GeneradorQueCaptura()
    _use_case(db, generador).ejecutar("¿Qué alertas tengo activas?", organizacion_id="org-a", usuario_id="u-a")

    contexto = generador.contextos[0]
    assert "ALERTA_ORG_A" in contexto and "Medidor A" in contexto
    assert "ALERTA_ORG_B" not in contexto
    assert "Medidor B" not in contexto
    assert "dev-b" not in contexto


def test_caso_de_uso_rechaza_organizacion_vacia(db: Session):
    generador = GeneradorQueCaptura()
    with pytest.raises(ValueError):
        _use_case(db, generador).ejecutar("¿Qué alertas tengo activas?", organizacion_id="", usuario_id="u")
    assert generador.contextos == []


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "u", "rol": "operador"},
        {"sub": "u", "rol": "superadmin"},
        {"sub": "u", "rol": "invitado_global", "organizacion_id": "org-a"},
    ],
)
def test_router_sin_claim_org_responde_404_sin_llamar_al_caso_de_uso(claims):
    app = create_app()
    app.include_router(asistente_router)
    use_case = MagicMock()
    app.dependency_overrides[get_usuario_actual] = lambda: claims
    app.dependency_overrides[get_procesar_pregunta_asistente_use_case] = lambda: use_case

    response = TestClient(app).post("/api/v1/asistente/preguntar", json={"pregunta": "¿alertas?"})

    assert response.status_code == 404
    use_case.ejecutar.assert_not_called()


def test_router_pasa_la_claim_org_al_caso_de_uso():
    app = create_app()
    app.include_router(asistente_router)
    use_case = MagicMock()
    use_case.ejecutar.return_value = MagicMock(texto="ok", intencion="EXPLICAR_ALERTAS")
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u-a", "rol": "operador", "org": "org-a"}
    app.dependency_overrides[get_procesar_pregunta_asistente_use_case] = lambda: use_case

    response = TestClient(app).post("/api/v1/asistente/preguntar", json={"pregunta": "¿alertas?"})

    assert response.status_code == 200
    assert use_case.ejecutar.call_args.kwargs["organizacion_id"] == "org-a"
    assert use_case.ejecutar.call_args.kwargs["usuario_id"] == "u-a"

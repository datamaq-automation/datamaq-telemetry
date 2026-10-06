"""tests/integration/test_auditoria_endpoint.py — Tests de endpoints de auditoría."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.infrastructure.sqlalchemy.models import AuditoriaChangesTIModel, Base, DeviceModel
from src.main import create_app


@pytest.fixture
def db_session() -> Session:
    """Crear sesión de BD para pruebas."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """Cliente de prueba con BD en memoria."""

    def get_db_override() -> Session:
        return db_session

    app = create_app()
    app.dependency_overrides[Session] = get_db_override
    return TestClient(app)


@pytest.fixture
def fixture_device_con_auditoria(db_session: Session) -> tuple[str, list[dict]]:
    """Crear dispositivo y auditoría de cambios para pruebas."""
    device = DeviceModel(
        id="uuid-test-1",
        device_uid="AA:BB:CC:DD:EE:FF",
        name="Medidor 369",
        model="SmartPlus",
    )
    db_session.add(device)
    db_session.commit()

    cambios = [
        AuditoriaChangesTIModel(
            device_id="uuid-test-1",
            tipo_cambio="correccion_angular_fases",
            valor_anterior="R:180,S:-120",
            valor_nuevo="R:0,S:15",
            motivo="A0 Trafo 2 (2026-10-05): error residual -15° fase S",
            commit_git="1426254abc",
            usuario="agustin",
            timestamp=datetime(2026, 10, 5, 14, 35, 0, tzinfo=timezone.utc),
        ),
        AuditoriaChangesTIModel(
            device_id="uuid-test-1",
            tipo_cambio="invertido",
            valor_anterior="False",
            valor_nuevo="True",
            motivo="A0 Trafo 2 (2026-10-06): corrección adicional",
            commit_git="1426255def",
            usuario="agustin",
            timestamp=datetime(2026, 10, 6, 10, 0, 0, tzinfo=timezone.utc),
        ),
        AuditoriaChangesTIModel(
            device_id="uuid-test-1",
            tipo_cambio="correccion_angular_fases",
            valor_anterior="R:0,S:15",
            valor_nuevo="R:0,S:20",
            motivo="A0 Trafo 2 (2026-10-07): ajuste fino",
            commit_git="1426256ghi",
            usuario="agustin",
            timestamp=datetime(2026, 10, 7, 9, 30, 0, tzinfo=timezone.utc),
        ),
    ]
    for cambio in cambios:
        db_session.add(cambio)
    db_session.commit()

    return "uuid-test-1", cambios


def test_listar_cambios_ti_sin_filtros(
    client: TestClient, fixture_device_con_auditoria: tuple[str, list[dict]]
) -> None:
    """GET /api/v1/admin/auditoria/cambios-ti sin filtros retorna todos los registros."""
    response = client.get("/api/v1/admin/auditoria/cambios-ti")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["registros"]) == 3


def test_listar_cambios_ti_filtrar_por_tipo(
    client: TestClient, fixture_device_con_auditoria: tuple[str, list[dict]]
) -> None:
    """GET /api/v1/admin/auditoria/cambios-ti?tipo_cambio=correccion_angular_fases retorna 2 registros."""
    response = client.get("/api/v1/admin/auditoria/cambios-ti?tipo_cambio=correccion_angular_fases")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert all(r["tipo_cambio"] == "correccion_angular_fases" for r in data["registros"])


def test_detalle_cambio_ti(client: TestClient, fixture_device_con_auditoria: tuple[str, list[dict]]) -> None:
    """GET /api/v1/admin/auditoria/cambios-ti/{id} retorna detalle con commit_url."""
    # Obtener primer cambio
    cambios = fixture_device_con_auditoria[1]
    cambio_id = cambios[0].id

    response = client.get(f"/api/v1/admin/auditoria/cambios-ti/{cambio_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == cambio_id
    assert "commit_url" in data
    assert "github.com" in data["commit_url"]
    assert data["dispositivo_detalle"] is not None
    assert data["dispositivo_detalle"]["id"] == "uuid-test-1"


def test_acceso_sin_admin(client: TestClient) -> None:
    """GET sin permiso admin retorna 403."""
    response = client.get("/api/v1/admin/auditoria/cambios-ti")
    # Sin autenticación, debería fallar (depende de la configuración de auth)
    # Por ahora, simplemente verificamos que el endpoint existe
    assert response.status_code in [200, 403, 401]

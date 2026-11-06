"""tests/integration/test_dispositivos_api.py — Pruebas de integración de la API de dispositivos: registro de rutas y acceso protegido."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.dispositivo_dto import DispositivoResponseDTO
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import (
    get_dispositivos_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.server import create_app


def _rutas_dispositivos(app) -> dict[str, set[str]]:
    rutas: dict[str, set[str]] = {}
    for ruta in app.routes:
        if hasattr(ruta, "methods") and hasattr(ruta, "path"):
            rutas.setdefault(ruta.path, set()).update(ruta.methods or set())
        elif hasattr(ruta, "original_router"):
            for subruta in ruta.original_router.routes:
                if hasattr(subruta, "methods") and hasattr(subruta, "path"):
                    rutas.setdefault(subruta.path, set()).update(subruta.methods or set())
    return {k: v for k, v in rutas.items() if k.startswith("/api/v1/dispositivos")}


def test_create_app_registra_rutas_dispositivos():
    app = create_app()
    rutas = _rutas_dispositivos(app)

    assert "/api/v1/dispositivos" in rutas
    assert "GET" in rutas["/api/v1/dispositivos"]
    assert "POST" in rutas["/api/v1/dispositivos"]

    assert "/api/v1/dispositivos/{device_id}" in rutas
    assert "GET" in rutas["/api/v1/dispositivos/{device_id}"]
    assert "PUT" in rutas["/api/v1/dispositivos/{device_id}"]


def test_listar_dispositivos_end_to_end():
    app = create_app()
    ahora = datetime.now(timezone.utc)

    mock_dto = DispositivoResponseDTO(
        id="dev-1",
        device_uid="PM-001",
        nombre="Tablero General",
        modelo="SmartPlus",
        planta_id=None,
        numero_serie="SN123",
        version_hw="v2.1",
        version_fw="v1.4.2",
        ubicacion_tag="Nave A",
        esta_activo=True,
        tipo_instalacion="CONSUMO",
        fases_con_ti="R,S,T",
        estado="ONLINE",
        visto_por_ultima_vez=None,
        creado_en=ahora,
        actualizado_en=ahora,
    )

    mock_use_case = MagicMock()
    mock_use_case.listar_dispositivos.return_value = [mock_dto]
    mock_acceso = MagicMock()
    # Un usuario con alguna planta permitida recibe una planta efectiva (la activa). None sería "ninguna" (datamaq#125).
    mock_acceso.resolver_planta_permitida.return_value = "planta-1"

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "operador", "org": "org-test"}
    app.dependency_overrides[get_dispositivos_use_case] = lambda: mock_use_case
    app.dependency_overrides[get_acceso_plantas_use_case] = lambda: mock_acceso

    client = TestClient(app)
    response = client.get("/api/v1/dispositivos")

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    data = response.json()
    assert len(data) == 1
    assert data[0]["device_uid"] == "PM-001"
    mock_acceso.resolver_planta_permitida.assert_called_once_with("user-test", "operador", "org-test", None)
    mock_use_case.listar_dispositivos.assert_called_once_with("planta-1", organizacion_id="org-test")


def test_listar_dispositivos_rechaza_planta_ajena():
    """Verifica que el endpoint rechaza acceso a plantas de otras organizaciones (IDOR fix)."""
    app = create_app()

    mock_use_case = MagicMock()
    mock_acceso = MagicMock()
    mock_acceso.resolver_planta_permitida.side_effect = PlantaNoEncontradaError(
        "Planta con id 'foreign-planta-id' no encontrada."
    )
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": "user-org-1",
        "rol": "operador",
        "org": "org-1",
    }
    app.dependency_overrides[get_dispositivos_use_case] = lambda: mock_use_case
    app.dependency_overrides[get_acceso_plantas_use_case] = lambda: mock_acceso

    client = TestClient(app)

    # Intento de acceso a planta de otra org debe devolver 404
    response = client.get("/api/v1/dispositivos?planta_id=foreign-planta-id")
    assert response.status_code == 404
    assert response.json()["detail"] == "planta_no_encontrada"

    # El use_case nunca debe ser llamado para plantas ajenas
    mock_use_case.listar_dispositivos.assert_not_called()
    mock_acceso.resolver_planta_permitida.assert_called_once_with(
        "user-org-1", "operador", "org-1", "foreign-planta-id"
    )

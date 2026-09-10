"""Pruebas de integración de la API de grupos de dispositivos (suma de lecturas de varios medidores)."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.grupo_dispositivos_dto import (
    GrupoDispositivosResponseDTO,
    ResumenGrupoDispositivosDTO,
)
from src.application.dtos.telemetria_dto import EnergiaAgregadaDTO
from src.infrastructure.fastapi.dependencies import (
    get_consultar_grupo_dispositivos_use_case,
    get_grupos_dispositivos_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_grupo_dispositivos
from src.infrastructure.fastapi.server import create_app


def _rutas_grupos(app) -> dict[str, set[str]]:
    rutas: dict[str, set[str]] = {}
    for ruta in app.routes:
        if hasattr(ruta, "methods") and hasattr(ruta, "path"):
            rutas.setdefault(ruta.path, set()).update(ruta.methods or set())
        elif hasattr(ruta, "original_router"):
            for subruta in ruta.original_router.routes:
                if hasattr(subruta, "methods") and hasattr(subruta, "path"):
                    rutas.setdefault(subruta.path, set()).update(subruta.methods or set())
    return {k: v for k, v in rutas.items() if k.startswith("/api/v1/grupos-dispositivos")}


def test_create_app_registra_rutas_grupos_dispositivos():
    app = create_app()
    rutas = _rutas_grupos(app)

    assert "/api/v1/grupos-dispositivos" in rutas
    assert "GET" in rutas["/api/v1/grupos-dispositivos"]
    assert "POST" in rutas["/api/v1/grupos-dispositivos"]
    assert "/api/v1/grupos-dispositivos/{grupo_id}/resumen" in rutas


def test_crear_grupo_end_to_end():
    app = create_app()
    mock_use_case = MagicMock()
    mock_use_case.crear_grupo.return_value = GrupoDispositivosResponseDTO(
        id="g1",
        planta_id="planta-durax",
        nombre="Total Planta",
        dispositivos_ids=["trafo-01", "trafo-02"],
        creado_en="2026-09-10T00:00:00Z",
        actualizado_en="2026-09-10T00:00:00Z",
    )

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "admin", "org": "org-a"}
    app.dependency_overrides[get_grupos_dispositivos_use_case] = lambda: mock_use_case

    client = TestClient(app)
    response = client.post(
        "/api/v1/grupos-dispositivos",
        json={"planta_id": "planta-durax", "nombre": "Total Planta", "dispositivos_ids": ["trafo-01", "trafo-02"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dispositivos_ids"] == ["trafo-01", "trafo-02"]


def test_crear_grupo_rechazado_para_invitado():
    app = create_app()
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "invitado", "org": "org-a"}
    app.dependency_overrides[get_grupos_dispositivos_use_case] = lambda: MagicMock()

    client = TestClient(app)
    response = client.post(
        "/api/v1/grupos-dispositivos",
        json={"planta_id": "planta-durax", "nombre": "Total Planta", "dispositivos_ids": []},
    )

    assert response.status_code == 403


def test_resumen_grupo_suma_potencia_y_energia_end_to_end():
    app = create_app()
    mock_use_case = MagicMock()
    mock_use_case.resumen.return_value = ResumenGrupoDispositivosDTO(
        grupo_id="g1",
        potencia_activa_total_w=2500.0,
        dispositivos_sin_dato=[],
        energia_agregada=[EnergiaAgregadaDTO(periodo="2026-09-02", energia_activa_neta_kwh=15.0)],
    )

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "operador", "org": "org-a"}
    app.dependency_overrides[verificar_propiedad_grupo_dispositivos] = lambda: None
    app.dependency_overrides[get_consultar_grupo_dispositivos_use_case] = lambda: mock_use_case

    client = TestClient(app)
    response = client.get("/api/v1/grupos-dispositivos/g1/resumen?granularity=day&dias=7")

    assert response.status_code == 200
    data = response.json()
    assert data["potencia_activa_total_w"] == 2500.0
    assert data["energia_agregada"][0]["energia_activa_neta_kwh"] == 15.0

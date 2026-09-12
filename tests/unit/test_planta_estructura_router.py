"""tests/unit/test_planta_estructura_router.py — Tests unitarios para el router de estructura de planta (unifilar y layout)."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.planta_estructura_dto import (
    CoordenadasZonaDTO,
    DispositivoLayoutDTO,
    GuardarLayoutRequestDTO,
    GuardarUnifilarRequestDTO,
    LayoutPlantaDTO,
    NodoUnifilarDTO,
    PosicionLayoutDTO,
    UnifilarPlantaDTO,
    ZonaPlantaDTO,
)
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.infrastructure.fastapi.dependencies import (
    get_planta_estructura_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.server import create_app


def _sample_unifilar_dto(planta_id: str = "planta-1") -> UnifilarPlantaDTO:
    return UnifilarPlantaDTO(
        planta_id=planta_id,
        nombre_planta="Planta Central",
        nodos=[
            NodoUnifilarDTO(
                id="n-1",
                parent_id=None,
                nombre="Acometida MT",
                tipo="acometida",
                device_id="dev-100",
                tension_nominal_V=13200.0,
                capacidad_nominal_kVA=1000.0,
                orden=0,
            )
        ],
    )


def _sample_layout_dto(planta_id: str = "planta-1") -> LayoutPlantaDTO:
    return LayoutPlantaDTO(
        planta_id=planta_id,
        nombre_planta="Planta Central",
        plano_svg_url="https://cdn.datamaq.com.ar/svg/layout.svg",
        zonas=[
            ZonaPlantaDTO(
                id="z-1",
                nombre="Nave A",
                coordenadas=CoordenadasZonaDTO(
                    x_porcentaje=10.0,
                    y_porcentaje=15.0,
                    ancho_porcentaje=40.0,
                    alto_porcentaje=30.0,
                ),
            )
        ],
        dispositivos=[
            DispositivoLayoutDTO(
                device_id="dev-100",
                zona_id="z-1",
                posicion=PosicionLayoutDTO(x_porcentaje=20.0, y_porcentaje=25.0),
            )
        ],
    )


def _cliente(rol: str = "admin") -> tuple[TestClient, MagicMock]:
    app = create_app()
    mock_use_case = MagicMock()
    app.dependency_overrides[get_planta_estructura_use_case] = lambda: mock_use_case
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": "u1",
        "rol": rol,
        "org": "org-1",
    }
    return TestClient(app), mock_use_case


# ============================================================================
# DIAGRAMA UNIFILAR
# ============================================================================


def test_get_unifilar_default_exitoso_sin_planta_id():
    client, mock_use_case = _cliente()
    dto = _sample_unifilar_dto()
    mock_use_case.obtener_unifilar.return_value = dto

    response = client.get("/api/v1/planta/unifilar")

    assert response.status_code == 200
    mock_use_case.obtener_unifilar.assert_called_once_with(planta_id=None)
    data = response.json()
    assert data["planta_id"] == "planta-1"
    assert len(data["nodos"]) == 1
    assert data["nodos"][0]["id"] == "n-1"


def test_get_unifilar_default_exitoso_con_planta_id_query():
    client, mock_use_case = _cliente()
    dto = _sample_unifilar_dto(planta_id="planta-custom")
    mock_use_case.obtener_unifilar.return_value = dto

    response = client.get("/api/v1/planta/unifilar?planta_id=planta-custom")

    assert response.status_code == 200
    mock_use_case.obtener_unifilar.assert_called_once_with(planta_id="planta-custom")
    assert response.json()["planta_id"] == "planta-custom"


def test_get_unifilar_default_planta_no_encontrada():
    client, mock_use_case = _cliente()
    mock_use_case.obtener_unifilar.side_effect = PlantaNoEncontradaError("Planta no existe")

    response = client.get("/api/v1/planta/unifilar")

    assert response.status_code == 404
    assert "Planta no existe" in response.json()["detail"]


def test_get_unifilar_default_error_interno():
    client, mock_use_case = _cliente()
    mock_use_case.obtener_unifilar.side_effect = RuntimeError("Fallo inesperado")

    response = client.get("/api/v1/planta/unifilar")

    assert response.status_code == 500
    assert "error interno" in response.json()["detail"].lower()


def test_get_unifilar_by_planta_exitoso():
    client, mock_use_case = _cliente()
    dto = _sample_unifilar_dto(planta_id="planta-42")
    mock_use_case.obtener_unifilar.return_value = dto

    response = client.get("/api/v1/plantas/planta-42/unifilar")

    assert response.status_code == 200
    mock_use_case.obtener_unifilar.assert_called_once_with(planta_id="planta-42")
    assert response.json()["planta_id"] == "planta-42"


def test_get_unifilar_by_planta_no_encontrada():
    client, mock_use_case = _cliente()
    mock_use_case.obtener_unifilar.side_effect = PlantaNoEncontradaError("Planta 42 no existe")

    response = client.get("/api/v1/plantas/planta-42/unifilar")

    assert response.status_code == 404
    assert "Planta 42 no existe" in response.json()["detail"]


def test_get_unifilar_by_planta_error_interno():
    client, mock_use_case = _cliente()
    mock_use_case.obtener_unifilar.side_effect = Exception("Error de base de datos")

    response = client.get("/api/v1/plantas/planta-42/unifilar")

    assert response.status_code == 500
    assert "error interno" in response.json()["detail"].lower()


def test_update_unifilar_exitoso():
    client, mock_use_case = _cliente(rol="admin")
    dto = _sample_unifilar_dto(planta_id="planta-42")
    mock_use_case.guardar_unifilar.return_value = dto

    payload = {
        "nodos": [
            {
                "id": "n-1",
                "parent_id": None,
                "nombre": "Acometida MT",
                "tipo": "acometida",
                "device_id": "dev-100",
                "tension_nominal_V": 13200.0,
                "capacidad_nominal_kVA": 1000.0,
                "orden": 0,
            }
        ]
    }

    response = client.put("/api/v1/plantas/planta-42/unifilar", json=payload)

    assert response.status_code == 200
    mock_use_case.guardar_unifilar.assert_called_once()
    call_args = mock_use_case.guardar_unifilar.call_args
    assert call_args.kwargs["planta_id"] == "planta-42"
    assert isinstance(call_args.kwargs["dto"], GuardarUnifilarRequestDTO)
    assert len(call_args.kwargs["dto"].nodos) == 1
    assert response.json()["planta_id"] == "planta-42"


def test_update_unifilar_rol_invitado_forbidden():
    client, mock_use_case = _cliente(rol="invitado")
    payload = {"nodos": []}

    response = client.put("/api/v1/plantas/planta-42/unifilar", json=payload)

    assert response.status_code == 403
    mock_use_case.guardar_unifilar.assert_not_called()


def test_update_unifilar_payload_invalido():
    client, mock_use_case = _cliente(rol="admin")
    # Falta 'nodos' en el body
    response = client.put("/api/v1/plantas/planta-42/unifilar", json={})

    assert response.status_code == 422
    mock_use_case.guardar_unifilar.assert_not_called()


def test_update_unifilar_planta_no_encontrada():
    client, mock_use_case = _cliente(rol="admin")
    mock_use_case.guardar_unifilar.side_effect = PlantaNoEncontradaError("Planta no encontrada")

    payload = {"nodos": []}
    response = client.put("/api/v1/plantas/planta-999/unifilar", json=payload)

    assert response.status_code == 404
    assert "Planta no encontrada" in response.json()["detail"]


def test_update_unifilar_error_interno():
    client, mock_use_case = _cliente(rol="admin")
    mock_use_case.guardar_unifilar.side_effect = RuntimeError("Falla al guardar unifilar")

    payload = {"nodos": []}
    response = client.put("/api/v1/plantas/planta-42/unifilar", json=payload)

    assert response.status_code == 500
    assert "error interno" in response.json()["detail"].lower()


# ============================================================================
# LAYOUT 2D DE PLANTA
# ============================================================================


def test_get_layout_default_exitoso_sin_planta_id():
    client, mock_use_case = _cliente()
    dto = _sample_layout_dto()
    mock_use_case.obtener_layout.return_value = dto

    response = client.get("/api/v1/planta/layout")

    assert response.status_code == 200
    mock_use_case.obtener_layout.assert_called_once_with(planta_id=None)
    data = response.json()
    assert data["planta_id"] == "planta-1"
    assert len(data["zonas"]) == 1
    assert len(data["dispositivos"]) == 1


def test_get_layout_default_exitoso_con_planta_id_query():
    client, mock_use_case = _cliente()
    dto = _sample_layout_dto(planta_id="planta-custom")
    mock_use_case.obtener_layout.return_value = dto

    response = client.get("/api/v1/planta/layout?planta_id=planta-custom")

    assert response.status_code == 200
    mock_use_case.obtener_layout.assert_called_once_with(planta_id="planta-custom")
    assert response.json()["planta_id"] == "planta-custom"


def test_get_layout_default_planta_no_encontrada():
    client, mock_use_case = _cliente()
    mock_use_case.obtener_layout.side_effect = PlantaNoEncontradaError("Planta no existe")

    response = client.get("/api/v1/planta/layout")

    assert response.status_code == 404
    assert "Planta no existe" in response.json()["detail"]


def test_get_layout_default_error_interno():
    client, mock_use_case = _cliente()
    mock_use_case.obtener_layout.side_effect = RuntimeError("Fallo inesperado")

    response = client.get("/api/v1/planta/layout")

    assert response.status_code == 500
    assert "error interno" in response.json()["detail"].lower()


def test_get_layout_by_planta_exitoso():
    client, mock_use_case = _cliente()
    dto = _sample_layout_dto(planta_id="planta-88")
    mock_use_case.obtener_layout.return_value = dto

    response = client.get("/api/v1/plantas/planta-88/layout")

    assert response.status_code == 200
    mock_use_case.obtener_layout.assert_called_once_with(planta_id="planta-88")
    assert response.json()["planta_id"] == "planta-88"


def test_get_layout_by_planta_no_encontrada():
    client, mock_use_case = _cliente()
    mock_use_case.obtener_layout.side_effect = PlantaNoEncontradaError("Planta 88 no existe")

    response = client.get("/api/v1/plantas/planta-88/layout")

    assert response.status_code == 404
    assert "Planta 88 no existe" in response.json()["detail"]


def test_get_layout_by_planta_error_interno():
    client, mock_use_case = _cliente()
    mock_use_case.obtener_layout.side_effect = Exception("Fallo inesperado")

    response = client.get("/api/v1/plantas/planta-88/layout")

    assert response.status_code == 500
    assert "error interno" in response.json()["detail"].lower()


def test_update_layout_exitoso():
    client, mock_use_case = _cliente(rol="admin")
    dto = _sample_layout_dto(planta_id="planta-88")
    mock_use_case.guardar_layout.return_value = dto

    payload = {
        "plano_svg_url": "https://cdn.datamaq.com.ar/svg/layout.svg",
        "zonas": [
            {
                "id": "z-1",
                "nombre": "Nave A",
                "coordenadas": {
                    "x_porcentaje": 10.0,
                    "y_porcentaje": 15.0,
                    "ancho_porcentaje": 40.0,
                    "alto_porcentaje": 30.0,
                },
            }
        ],
        "dispositivos": [
            {
                "device_id": "dev-100",
                "zona_id": "z-1",
                "posicion": {
                    "x_porcentaje": 20.0,
                    "y_porcentaje": 25.0,
                },
            }
        ],
    }

    response = client.put("/api/v1/plantas/planta-88/layout", json=payload)

    assert response.status_code == 200
    mock_use_case.guardar_layout.assert_called_once()
    call_args = mock_use_case.guardar_layout.call_args
    assert call_args.kwargs["planta_id"] == "planta-88"
    assert isinstance(call_args.kwargs["dto"], GuardarLayoutRequestDTO)
    assert response.json()["planta_id"] == "planta-88"


def test_update_layout_rol_invitado_forbidden():
    client, mock_use_case = _cliente(rol="invitado")
    payload = {"plano_svg_url": None, "zonas": [], "dispositivos": []}

    response = client.put("/api/v1/plantas/planta-88/layout", json=payload)

    assert response.status_code == 403
    mock_use_case.guardar_layout.assert_not_called()


def test_update_layout_coordenadas_invalidas_validation_error():
    client, mock_use_case = _cliente(rol="admin")
    payload = {
        "plano_svg_url": None,
        "zonas": [
            {
                "id": "z-1",
                "nombre": "Nave Invalida",
                "coordenadas": {
                    "x_porcentaje": 150.0,  # Máximo es 100.0
                    "y_porcentaje": 10.0,
                    "ancho_porcentaje": 20.0,
                    "alto_porcentaje": 20.0,
                },
            }
        ],
        "dispositivos": [],
    }

    response = client.put("/api/v1/plantas/planta-88/layout", json=payload)

    assert response.status_code == 422
    mock_use_case.guardar_layout.assert_not_called()


def test_update_layout_planta_no_encontrada():
    client, mock_use_case = _cliente(rol="admin")
    mock_use_case.guardar_layout.side_effect = PlantaNoEncontradaError("Planta 88 no existe")

    payload = {"plano_svg_url": None, "zonas": [], "dispositivos": []}
    response = client.put("/api/v1/plantas/planta-88/layout", json=payload)

    assert response.status_code == 404
    assert "Planta 88 no existe" in response.json()["detail"]


def test_update_layout_error_interno():
    client, mock_use_case = _cliente(rol="admin")
    mock_use_case.guardar_layout.side_effect = RuntimeError("Error guardando layout")

    payload = {"plano_svg_url": None, "zonas": [], "dispositivos": []}
    response = client.put("/api/v1/plantas/planta-88/layout", json=payload)

    assert response.status_code == 500
    assert "error interno" in response.json()["detail"].lower()


# ============================================================================
# ESTADÍSTICAS DE ÁREAS (ISA-95 NIVEL 2)
# ============================================================================


def test_get_areas_estadisticas_default_exitoso():
    client, mock_use_case = _cliente()
    mock_use_case.obtener_areas_estadisticas.return_value = {
        "planta_id": "planta-1",
        "superficie_total_m2": 3500.0,
        "areas": [
            {
                "area_id": "area-1",
                "nombre": "Zona Forja",
                "superficie_m2": 1500.0,
                "lineas_count": 1,
                "dispositivos_activos_count": 2,
                "dispositivos_total_count": 2,
                "carga_promedio_kw": 120.0,
                "coordenadas_layout": None,
            }
        ],
    }

    response = client.get("/api/v1/planta/areas")

    assert response.status_code == 200
    mock_use_case.obtener_areas_estadisticas.assert_called_once_with(planta_id=None)
    data = response.json()
    assert data["planta_id"] == "planta-1"
    assert data["superficie_total_m2"] == 3500.0
    assert len(data["areas"]) == 1
    assert data["areas"][0]["area_id"] == "area-1"


def test_get_areas_estadisticas_by_planta_exitoso():
    client, mock_use_case = _cliente()
    mock_use_case.obtener_areas_estadisticas.return_value = {
        "planta_id": "planta-durax",
        "superficie_total_m2": 9000.0,
        "areas": [],
    }

    response = client.get("/api/v1/plantas/planta-durax/areas")

    assert response.status_code == 200
    mock_use_case.obtener_areas_estadisticas.assert_called_once_with(planta_id="planta-durax")
    assert response.json()["planta_id"] == "planta-durax"

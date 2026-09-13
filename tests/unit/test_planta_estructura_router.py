"""tests/unit/test_planta_estructura_router.py — Tests unitarios para el router de estructura de planta (unifilar y layout)."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.planta_estructura_dto import (
    CoordenadasZonaDTO,
    DispositivoLayoutDTO,
    LayoutPlantaDTO,
    NodoUnifilarDTO,
    PosicionLayoutDTO,
    ResumenNodoUnifilarDTO,
    UnifilarPlantaDTO,
    ZonaPlantaDTO,
)
from src.domain.telemetria.exceptions import (
    NodoUnifilarNoEncontradoError,
    PlantaNoEncontradaError,
)
from src.infrastructure.fastapi.dependencies import (
    get_consultar_nodo_unifilar_use_case,
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
    app.dependency_overrides[get_consultar_nodo_unifilar_use_case] = lambda: mock_use_case
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
    mock_use_case.obtener_unifilar.assert_called_once_with(planta_id=None, organizacion_id="org-1")
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
    mock_use_case.obtener_unifilar.assert_called_once_with(planta_id="planta-custom", organizacion_id="org-1")
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


def test_put_unifilar_ya_no_existe():
    """La estructura se edita por commit al YAML; la API no expone escritura."""
    client, mock_use_case = _cliente()
    response = client.put("/api/v1/plantas/planta-42/unifilar", json={"nodos": []})
    assert response.status_code == 405
    mock_use_case.guardar_unifilar.assert_not_called()


# ============================================================================
# LAYOUT 2D DE PLANTA
# ============================================================================


def test_get_layout_default_exitoso_sin_planta_id():
    client, mock_use_case = _cliente()
    dto = _sample_layout_dto()
    mock_use_case.obtener_layout.return_value = dto

    response = client.get("/api/v1/planta/layout")

    assert response.status_code == 200
    mock_use_case.obtener_layout.assert_called_once_with(planta_id=None, organizacion_id="org-1")
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
    mock_use_case.obtener_layout.assert_called_once_with(planta_id="planta-custom", organizacion_id="org-1")
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


def test_put_layout_ya_no_existe():
    client, mock_use_case = _cliente()
    response = client.put("/api/v1/plantas/planta-88/layout", json={"zonas": []})
    assert response.status_code == 405
    mock_use_case.guardar_layout.assert_not_called()


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
                "dispositivo_ids": ["d-1", "d-2"],
                "coordenadas_layout": None,
            }
        ],
    }

    response = client.get("/api/v1/planta/areas")

    assert response.status_code == 200
    mock_use_case.obtener_areas_estadisticas.assert_called_once_with(planta_id=None, organizacion_id="org-1")
    data = response.json()
    assert data["planta_id"] == "planta-1"
    assert data["superficie_total_m2"] == 3500.0
    assert len(data["areas"]) == 1
    assert data["areas"][0]["area_id"] == "area-1"
    assert data["areas"][0]["dispositivo_ids"] == ["d-1", "d-2"]


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


# ============================================================================
# TELEMETRÍA AGREGADA POR NODO DEL UNIFILAR
# ============================================================================


def test_resumen_nodo_unifilar_exitoso():
    client, mock_use_case = _cliente()
    mock_use_case.resumen.return_value = ResumenNodoUnifilarDTO(
        planta_id="planta-1",
        nodo_id="mt",
        es_virtual=True,
        dispositivos_ids=["dev-1", "dev-2"],
        potencia_activa_total_w=450000.0,
    )

    response = client.get("/api/v1/plantas/planta-1/unifilar/nodos/mt/resumen?granularity=day&dias=7")

    assert response.status_code == 200
    mock_use_case.resumen.assert_called_once_with("planta-1", "mt", "org-1", "day", "America/Argentina/Buenos_Aires", 7)
    data = response.json()
    assert data["es_virtual"] is True
    assert data["dispositivos_ids"] == ["dev-1", "dev-2"]
    assert data["potencia_activa_total_w"] == 450000.0


def test_resumen_nodo_unifilar_superadmin_sin_org():
    client, mock_use_case = _cliente(rol="superadmin")
    mock_use_case.resumen.return_value = ResumenNodoUnifilarDTO(planta_id="planta-1", nodo_id="mt", es_virtual=True)

    response = client.get("/api/v1/plantas/planta-1/unifilar/nodos/mt/resumen")

    assert response.status_code == 200
    assert mock_use_case.resumen.call_args.args[2] is None


def test_resumen_nodo_unifilar_no_encontrado():
    client, mock_use_case = _cliente()
    mock_use_case.resumen.side_effect = NodoUnifilarNoEncontradoError("no existe")

    response = client.get("/api/v1/plantas/planta-1/unifilar/nodos/x/resumen")

    assert response.status_code == 404


def test_historico_nodo_unifilar_exitoso():
    client, mock_use_case = _cliente()
    mock_use_case.historico.return_value = []

    response = client.get("/api/v1/plantas/planta-1/unifilar/nodos/mt/resumen/historico?hours=6&granularity=15m")

    assert response.status_code == 200
    mock_use_case.historico.assert_called_once_with("planta-1", "mt", "org-1", "15m", 6)
    assert response.json() == []

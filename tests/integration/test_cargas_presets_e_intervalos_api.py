"""tests/integration/test_cargas_presets_e_intervalos_api.py — Pruebas de integración para endpoints de presets e intervalos de actividad por dispositivo."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.carga_dto import (
    IntervaloActividadResponseDTO,
)
from src.domain.cargas.entities import Carga
from src.domain.cargas.servicios.presets_cargas import CatalogoPresetsCargas
from src.domain.cargas.value_objects import (
    OrigenClasificacionCarga,
)
from src.infrastructure.fastapi.dependencies import (
    get_atribucion_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_dispositivo
from src.infrastructure.fastapi.routes.cargas_router import (
    verificar_acceso_a_campana,
    verificar_acceso_a_carga,
    verificar_acceso_a_intervalo,
    verificar_alta_de_campana,
    verificar_alta_de_carga,
    verificar_correccion_de_intervalo,
)
from src.infrastructure.fastapi.server import create_app

MEDIDOR_TEST = "dev-casa-test-endpoints"
AHORA = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


def _cliente(use_case: MagicMock, rol: str = "admin") -> TestClient:
    app = create_app()
    # La propiedad del medidor (#41) tiene sus propios tests; acá se prueba el comportamiento de cargas.
    app.dependency_overrides[verificar_propiedad_dispositivo] = lambda: None
    app.dependency_overrides[verificar_acceso_a_carga] = lambda: None
    app.dependency_overrides[verificar_acceso_a_campana] = lambda: None
    app.dependency_overrides[verificar_alta_de_carga] = lambda: None
    app.dependency_overrides[verificar_alta_de_campana] = lambda: None
    app.dependency_overrides[verificar_correccion_de_intervalo] = lambda: None
    app.dependency_overrides[verificar_acceso_a_intervalo] = lambda: None
    app.dependency_overrides[get_atribucion_use_case] = lambda: use_case
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u-admin", "rol": rol}
    return TestClient(app)


def test_obtener_presets_catalogo_devuelve_9_electrodomesticos():
    """GET /api/v1/cargas/presets devuelve las 9 cargas de catálogo estándar sin requerir base de datos."""
    mock_uc = MagicMock()
    cliente = _cliente(mock_uc, rol="viewer")

    res = cliente.get("/api/v1/cargas/presets")

    assert res.status_code == 200
    datos = res.json()
    assert len(datos) == 9
    nombres = {c["nombre"] for c in datos}
    assert "Heladera" in nombres
    assert "Pava eléctrica" in nombres
    assert "Termotanque eléctrico" in nombres
    assert "Computadora / PC" in nombres
    assert "Iluminación" in nombres


def test_inicializar_presets_requiere_escritura_y_delega_a_caso_de_uso():
    """POST /api/v1/cargas/presets/inicializar delega al caso de uso y rechaza a usuarios viewer."""
    mock_uc = MagicMock()
    presets: list[Carga] = CatalogoPresetsCargas.obtener_todas(MEDIDOR_TEST)
    mock_uc.inicializar_presets_catalogo.return_value = presets

    # Con rol viewer debe rechazar con 403
    cliente_viewer = _cliente(mock_uc, rol="invitado")
    res_viewer = cliente_viewer.post(f"/api/v1/cargas/presets/inicializar?device_id={MEDIDOR_TEST}")
    assert res_viewer.status_code == 403

    # Con rol admin debe autorizar y delegar
    cliente_admin = _cliente(mock_uc, rol="admin")
    res_admin = cliente_admin.post(f"/api/v1/cargas/presets/inicializar?device_id={MEDIDOR_TEST}")
    assert res_admin.status_code == 200
    mock_uc.inicializar_presets_catalogo.assert_called_once_with(MEDIDOR_TEST)
    datos = res_admin.json()
    assert len(datos) == 9


def test_listar_intervalos_dispositivo_delega_filtros():
    """GET /api/v1/cargas/intervalos delega los parámetros de filtro temporal y no-atribuidos."""
    mock_uc = MagicMock()
    mock_uc.listar_intervalos_dispositivo.return_value = [
        IntervaloActividadResponseDTO(
            id=101,
            dispositivo_id=MEDIDOR_TEST,
            carga_id=None,
            inicio_at=AHORA,
            fin_at=AHORA,
            duracion_segundos=1200.0,
            potencia_media_w=120.0,
            delta_reactiva_var=90.0,
            energia_kwh=0.04,
            confianza=0.88,
            origen=OrigenClasificacionCarga.REGLA,
            notas="Sugerido por regla: Heladera (88%)",
        )
    ]

    cliente = _cliente(mock_uc, rol="viewer")
    res = cliente.get(f"/api/v1/cargas/intervalos?device_id={MEDIDOR_TEST}&solo_no_atribuidos=true&dias=3")

    assert res.status_code == 200
    datos = res.json()
    assert len(datos) == 1
    assert datos[0]["carga_id"] is None
    assert "Sugerido por regla: Heladera" in datos[0]["notas"]
    mock_uc.listar_intervalos_dispositivo.assert_called_once()

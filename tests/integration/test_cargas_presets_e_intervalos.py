"""tests/integration/test_cargas_presets_e_intervalos.py."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.carga_dto import (
    IntervaloActividadResponseDTO,
)
from src.domain.cargas.entities import Carga
from src.domain.cargas.value_objects import (
    CategoriaCarga,
    NaturalezaElectrica,
    PatronOperacion,
)
from src.infrastructure.fastapi.dependencies import (
    get_atribucion_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.server import create_app

MEDIDOR_PRUEBA = "d48c49f0-3564-4000-8000-000000000001"
AHORA = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)


def _cliente_atribucion(use_case: MagicMock, rol: str = "admin") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_atribucion_use_case] = lambda: use_case
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": "usr-test-1",
        "username": "tester@datamaq.com.ar",
        "rol": rol,
    }
    return TestClient(app)


def test_obtener_presets_catalogo_devuelve_los_9_presets():
    use_case = MagicMock()
    cliente = _cliente_atribucion(use_case, rol="invitado")

    respuesta = cliente.get("/api/v1/cargas/presets")

    assert respuesta.status_code == 200
    presets = respuesta.json()
    assert isinstance(presets, list)
    assert len(presets) == 9
    nombres = [p["nombre"] for p in presets]
    assert "Heladera" in nombres
    assert "Freezer" in nombres
    assert "Pava eléctrica" in nombres


def test_inicializar_presets_requiere_escritura_y_device_id():
    use_case = MagicMock()
    carga_falsa = Carga(
        id="carga-1",
        dispositivo_id=MEDIDOR_PRUEBA,
        nombre="Heladera",
        categoria=CategoriaCarga.REFRIGERACION,
        naturaleza_electrica=NaturalezaElectrica.MOTOR,
        patron_operacion=PatronOperacion.CICLICO_TERMOSTATICO,
    )
    use_case.inicializar_presets_catalogo.return_value = [carga_falsa]

    # 1. Con usuario invitado -> 403 Forbidden
    cliente_invitado = _cliente_atribucion(use_case, rol="invitado")
    resp_inv = cliente_invitado.post(f"/api/v1/cargas/presets/inicializar?device_id={MEDIDOR_PRUEBA}")
    assert resp_inv.status_code == 403

    # 2. Con admin pero sin device_id -> 422 Unprocessable Entity
    cliente_admin = _cliente_atribucion(use_case, rol="admin")
    resp_sin_device = cliente_admin.post("/api/v1/cargas/presets/inicializar")
    assert resp_sin_device.status_code == 422

    # 3. Con admin y device_id -> 200 OK
    resp_ok = cliente_admin.post(f"/api/v1/cargas/presets/inicializar?device_id={MEDIDOR_PRUEBA}")
    assert resp_ok.status_code == 200
    cargas = resp_ok.json()
    assert len(cargas) == 1
    assert cargas[0]["nombre"] == "Heladera"
    use_case.inicializar_presets_catalogo.assert_called_once_with(MEDIDOR_PRUEBA)


def test_listar_intervalos_permite_filtrar_por_no_atribuidos():
    use_case = MagicMock()
    intervalo_dto = IntervaloActividadResponseDTO(
        id=101,
        dispositivo_id=MEDIDOR_PRUEBA,
        carga_id=None,
        nombre_carga=None,
        inicio_at=AHORA,
        fin_at=AHORA,
        duracion_segundos=120.0,
        potencia_media_w=1500.0,
        energia_kwh=0.05,
        esta_atribuido=False,
        confianza=None,
        es_imputacion_manual=False,
    )
    use_case.listar_intervalos_dispositivo.return_value = [intervalo_dto]

    cliente = _cliente_atribucion(use_case, rol="invitado")

    # 1. Consulta sin filtros
    resp = cliente.get(f"/api/v1/cargas/intervalos?device_id={MEDIDOR_PRUEBA}&solo_no_atribuidos=true&limite=50")

    assert resp.status_code == 200
    intervalos = resp.json()
    assert len(intervalos) == 1
    assert intervalos[0]["id"] == 101
    assert intervalos[0]["esta_atribuido"] is False

    use_case.listar_intervalos_dispositivo.assert_called_once_with(
        dispositivo_id=MEDIDOR_PRUEBA,
        desde=None,
        hasta=None,
        dias=7,
        solo_no_atribuidos=True,
        limite=50,
    )

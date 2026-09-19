# tests/unit/test_disponibilidad_router.py
from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.disponibilidad_dto import (
    EventoDisponibilidadResponseDTO,
    MetricasDisponibilidadOEEResponseDTO,
    ParadaProgramadaResponseDTO,
)
from src.application.dtos.maquina_dto import (
    HistogramaPotenciaResponseDTO,
    MaquinaResponseDTO,
)
from src.infrastructure.fastapi.dependencies import (
    get_disponibilidad_use_case,
    get_exportar_disponibilidad_use_case,
    get_maquinas_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.device_ownership import (
    verificar_propiedad_evento_disponibilidad,
    verificar_propiedad_maquina,
)
from src.infrastructure.fastapi.server import create_app

AHORA = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


def _maquina_response_dto(**kwargs) -> MaquinaResponseDTO:
    base = dict(
        id="maq-1",
        nombre="Línea de Envasado",
        dispositivo_id="dev-1",
        umbral_marcha_w=500.0,
        ventana_persistencia_lecturas=3,
        ventana_persistencia_segundos=15.0,
        esta_calibrada=True,
        creado_en=AHORA,
        actualizado_en=AHORA,
    )
    base.update(kwargs)
    return MaquinaResponseDTO(**base)


def _cliente() -> tuple[TestClient, dict[str, MagicMock]]:
    app = create_app()
    mocks = {
        "maquinas": MagicMock(),
        "disponibilidad": MagicMock(),
        "exportar": MagicMock(),
    }
    app.dependency_overrides[get_maquinas_use_case] = lambda: mocks["maquinas"]
    app.dependency_overrides[get_disponibilidad_use_case] = lambda: mocks["disponibilidad"]
    app.dependency_overrides[get_exportar_disponibilidad_use_case] = lambda: mocks["exportar"]
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": "u1",
        "rol": "admin",
        "org": "org-1",
    }
    app.dependency_overrides[verificar_propiedad_maquina] = lambda: None
    app.dependency_overrides[verificar_propiedad_evento_disponibilidad] = lambda: None
    return TestClient(app), mocks


def test_listar_maquinas_endpoint():
    client, mocks = _cliente()
    mocks["maquinas"].listar_maquinas.return_value = [_maquina_response_dto()]

    response = client.get("/api/v1/disponibilidad/maquinas")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "maq-1"


def test_obtener_maquina_endpoint():
    client, mocks = _cliente()
    mocks["maquinas"].obtener_maquina.return_value = _maquina_response_dto()

    response = client.get("/api/v1/disponibilidad/maquinas/maq-1")
    assert response.status_code == 200
    data = response.json()
    assert data["nombre"] == "Línea de Envasado"


def test_obtener_histograma_endpoint():
    client, mocks = _cliente()
    mocks["maquinas"].calcular_histograma.return_value = HistogramaPotenciaResponseDTO(
        dispositivo_id="dev-1",
        dias_analizados=7,
        cantidad_lecturas=100,
        bordes_bins_w=[0.0, 100.0, 500.0],
        frecuencias=[10, 50, 40],
        umbral_sugerido_w=1200.0,
    )

    response = client.get("/api/v1/disponibilidad/maquinas/maq-1/histograma?dias=7")
    assert response.status_code == 200
    data = response.json()
    assert data["umbral_sugerido_w"] == 1200.0


def test_listar_eventos_endpoint():
    client, mocks = _cliente()
    mocks["disponibilidad"].listar_eventos.return_value = [
        EventoDisponibilidadResponseDTO(
            id=1,
            maquina_id="maq-1",
            estado="PARADA",
            tipo_parada="NO_PROGRAMADA",
            inicio_at=AHORA,
            fin_at=AHORA,
            duracion_segundos=1800.0,
            origen="AUTOMATICA",
        )
    ]

    response = client.get("/api/v1/disponibilidad/maquinas/maq-1/eventos")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["tipo_parada"] == "NO_PROGRAMADA"


def test_obtener_metricas_oee_endpoint():
    client, mocks = _cliente()
    mocks["disponibilidad"].calcular_metricas_oee.return_value = MetricasDisponibilidadOEEResponseDTO(
        maquina_id="maq-1",
        periodo_inicio=AHORA,
        periodo_fin=AHORA,
        tiempo_total_segundos=604800.0,
        tiempo_marcha_segundos=504000.0,
        tiempo_parada_programada_segundos=36000.0,
        tiempo_parada_no_programada_segundos=64800.0,
        disponibilidad_oee_porcentaje=88.6,
    )

    response = client.get("/api/v1/disponibilidad/maquinas/maq-1/metricas-oee?dias=7")
    assert response.status_code == 200
    data = response.json()
    assert data["disponibilidad_oee_porcentaje"] == 88.6


def test_corregir_clasificacion_endpoint():
    client, mocks = _cliente()
    mocks["disponibilidad"].corregir_clasificacion.return_value = EventoDisponibilidadResponseDTO(
        id=1,
        maquina_id="maq-1",
        estado="PARADA",
        tipo_parada="PROGRAMADA",
        inicio_at=AHORA,
        fin_at=AHORA,
        duracion_segundos=1800.0,
        origen="CORRECCION_HUMANA",
    )

    payload = {"tipo_parada": "PROGRAMADA", "comentario": "Mantenimiento preventivo"}
    response = client.patch("/api/v1/disponibilidad/eventos/1/corregir", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["tipo_parada"] == "PROGRAMADA"


def test_listar_paradas_programadas_endpoint():
    client, mocks = _cliente()
    mocks["disponibilidad"].listar_paradas_programadas.return_value = [
        ParadaProgramadaResponseDTO(
            id="p-1",
            maquina_id="maq-1",
            inicio_at=AHORA,
            fin_at=AHORA,
            motivo="Limpieza",
            creado_en=AHORA,
        )
    ]

    response = client.get("/api/v1/disponibilidad/paradas-programadas?maquina_id=maq-1")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["motivo"] == "Limpieza"


def test_exportar_disponibilidad_csv_endpoint():
    client, mocks = _cliente()
    mocks["exportar"].exportar_csv.return_value = iter([b"fecha,duracion\n2026-09-04,1800\n"])

    response = client.get("/api/v1/disponibilidad/maquinas/maq-1/exportar/csv?dias=30")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]

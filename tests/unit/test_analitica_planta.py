# tests/unit/test_analitica_planta.py
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.application.use_cases.consultar_analitica_planta import ConsultarAnaliticaPlantaUseCase
from src.domain.telemetria.servicios.agregador_dispositivos import PuntoPotencia
from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.planta_ownership import resolver_planta_permitida
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import get_settings


def mock_get_usuario_actual():
    return {
        "user_id": "usr-test-123",
        "organizacion_id": "org-garin",
        "sub": "usr-test-123",
    }


def test_obtener_banco_capacitores_planta_exito():
    """Valida que /banco-capacitores/planta retorna datos reales (no simulados)."""
    app = create_app(get_settings())
    app.dependency_overrides[get_usuario_actual] = mock_get_usuario_actual
    app.dependency_overrides[resolver_planta_permitida] = lambda planta_id=None: planta_id

    client = TestClient(app)
    response = client.get("/api/v1/analitica/banco-capacitores/planta?planta_id=planta-garin")
    assert response.status_code == 200
    data = response.json()
    assert data["planta_id"] == "planta-garin"
    assert data["periodo_dias"] == 30  # Default: 30 días (ISO 50001)
    assert "potencia_activa_promedio_kw" in data  # Campo real (no hardcodeado)
    assert "potencia_reactiva_promedio_kvar" in data  # Campo nuevo para sobrecompensación
    assert "sobrecompensacion_sostenida" in data  # Flag para detección de Q<0


def test_obtener_penalizaciones_planta_exito():
    app = create_app(get_settings())
    app.dependency_overrides[get_usuario_actual] = mock_get_usuario_actual
    app.dependency_overrides[resolver_planta_permitida] = lambda planta_id=None: planta_id

    client = TestClient(app)
    response = client.get("/api/v1/analitica/penalizaciones/planta?planta_id=planta-garin")
    assert response.status_code == 200
    data = response.json()
    assert data["planta_id"] == "planta-garin"
    assert data["periodo_dias"] == 7
    assert data["horas_bajo_fp"] == 14.5
    assert data["penalizacion_estimada_ars"] > 0
    assert data["moneda"] == "ARS"


def _crear_punto_potencia_fake(
    fp: float = 0.996, potencia_w: float = 258600.0, q_var: float = 24000.0
) -> PuntoPotencia:
    """Crea punto de potencia ficticio con FP y reactiva controlables."""
    return PuntoPotencia(
        momento=datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
        potencia_activa_total_w=potencia_w,
        potencia_reactiva_total_var=q_var,
        potencia_aparente_total_va=(potencia_w**2 + q_var**2) ** 0.5,
        factor_desplazamiento_total=fp,
        dispositivos_sin_dato=[],
    )


def test_dimensionador_fp_alto_sin_recomendacion():
    """Valida que con FP > 0.95, NO se recomienda banco, aunque Q > 0."""
    mock_consultar = MagicMock()

    # Simular histórico con FP=0.996 (excelente) y Q>0 (inductiva)
    puntos = [_crear_punto_potencia_fake(fp=0.996, potencia_w=258600.0, q_var=24000.0) for _ in range(10)]

    with patch("src.application.use_cases.consultar_analitica_planta.calcular_historico", return_value=puntos):
        use_case = ConsultarAnaliticaPlantaUseCase(consultar_telemetria=mock_consultar)
        resultado = use_case.obtener_banco_capacitores(planta_id="planta-upp", periodo_dias=30)

    # Validaciones: FP alto → sin recomendación
    assert resultado.fp_promedio == 0.996
    assert resultado.potencia_reactiva_promedio_kvar > 0  # Q positiva (inductiva)
    assert resultado.banco_comercial_sugerido_kvar is None  # No se recomienda
    assert resultado.escalones_sugeridos_kvar == []
    assert resultado.razon_no_recomendacion is not None
    assert "0.95" in resultado.razon_no_recomendacion  # Menciona el umbral
    assert resultado.sobrecompensacion_sostenida is False  # Q>0, así que no está sobrecompensada


def test_dimensionador_fp_bajo_con_recomendacion():
    """Valida que con FP < 0.95 y Q > 0, SÍ se recomienda banco."""
    mock_consultar = MagicMock()

    # Simular histórico con FP=0.88 (bajo) y Q>0 (inductiva)
    puntos = [_crear_punto_potencia_fake(fp=0.88, potencia_w=120000.0, q_var=100000.0) for _ in range(10)]

    with patch("src.application.use_cases.consultar_analitica_planta.calcular_historico", return_value=puntos):
        use_case = ConsultarAnaliticaPlantaUseCase(consultar_telemetria=mock_consultar)
        resultado = use_case.obtener_banco_capacitores(planta_id="planta-test", periodo_dias=30)

    # Validaciones: FP bajo → sí se recomienda
    assert resultado.fp_promedio == 0.88
    assert resultado.banco_comercial_sugerido_kvar is not None  # Se recomienda
    assert resultado.razon_no_recomendacion is None  # Sin restricciones


def test_banco_capacitores_respeta_q_reactiva_negativa():
    """Valida que con Q <= 0 (régimen capacitivo), sobrecompensacion_sostenida=true y no se recomienda banco."""
    mock_consultar = MagicMock()

    # Simular histórico con Q negativa (capacitivo) o nula
    puntos_capacitivos = [
        _crear_punto_potencia_fake(fp=0.98, potencia_w=120000.0, q_var=-50000.0),  # Q negativa
        _crear_punto_potencia_fake(fp=0.98, potencia_w=120000.0, q_var=-30000.0),
        _crear_punto_potencia_fake(fp=0.99, potencia_w=120000.0, q_var=0.0),  # Q cero
    ]

    with patch("src.application.use_cases.consultar_analitica_planta.calcular_historico", return_value=puntos_capacitivos):
        use_case = ConsultarAnaliticaPlantaUseCase(consultar_telemetria=mock_consultar)
        resultado = use_case.obtener_banco_capacitores(planta_id="planta-capacitiva", periodo_dias=30)

    # Validaciones: Q_max <= 0 → sobrecompensada, no instalar banco
    assert resultado.potencia_reactiva_max_kvar == 0.0  # max([−50, −30, 0])
    assert resultado.sobrecompensacion_sostenida is True
    assert resultado.banco_comercial_sugerido_kvar is None
    assert resultado.razon_no_recomendacion is not None

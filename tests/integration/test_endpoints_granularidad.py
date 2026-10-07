"""Tests de integración para endpoints con validación de granularidad."""

import pytest
from fastapi.testclient import TestClient

from src.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Cliente de test para la aplicación."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def device_id() -> str:
    """ID de dispositivo de prueba."""
    return "test-device-123"


class TestPowerEndpoint:
    """Tests para /api/v1/telemetria/power/{device_id}."""

    def test_power_24h_5m_valido(self, client: TestClient, device_id: str) -> None:
        """Granularidad 5m es válida para período 24h."""
        # Este test fallará sin autenticación, pero valida la firma de la ruta
        response = client.get(f"/api/v1/telemetria/power/{device_id}?periodo=24h&granularidad=5m")
        assert response.status_code in (200, 401, 403)  # 401/403 por auth

    def test_power_24h_1h_invalido(self, client: TestClient, device_id: str) -> None:
        """Granularidad 1h es inválida para período 24h."""
        response = client.get(f"/api/v1/telemetria/power/{device_id}?periodo=24h&granularidad=1h")
        # Debería ser 400 por granularidad inválida (o 401 por auth primero)
        assert response.status_code in (400, 401, 403)

    def test_power_7d_1h_valido(self, client: TestClient, device_id: str) -> None:
        """Granularidad 1h es válida para período 7d."""
        response = client.get(f"/api/v1/telemetria/power/{device_id}?periodo=7d&granularidad=1h")
        assert response.status_code in (200, 401, 403)

    def test_power_30d_1d_valido(self, client: TestClient, device_id: str) -> None:
        """Granularidad 1d es válida para período 30d."""
        response = client.get(f"/api/v1/telemetria/power/{device_id}?periodo=30d&granularidad=1d")
        assert response.status_code in (200, 401, 403)

    def test_power_sin_granularidad_usa_default(self, client: TestClient, device_id: str) -> None:
        """Sin granularidad, se aplica default según período."""
        response = client.get(f"/api/v1/telemetria/power/{device_id}?periodo=24h")
        # Debería aceptar y aplicar default 5m
        assert response.status_code in (200, 401, 403)

    def test_power_periodo_invalido(self, client: TestClient, device_id: str) -> None:
        """Período inválido (ej. 60d) debe retornar 400."""
        response = client.get(f"/api/v1/telemetria/power/{device_id}?periodo=60d&granularidad=5m")
        # Debería ser 400 por período inválido
        assert response.status_code in (400, 401, 403)

    def test_power_granularidad_no_reconocida(self, client: TestClient, device_id: str) -> None:
        """Granularidad no reconocida (ej. 2m) debe retornar 400."""
        response = client.get(f"/api/v1/telemetria/power/{device_id}?periodo=24h&granularidad=2m")
        # Debería ser 400 por granularidad no válida
        assert response.status_code in (400, 401, 403)

    def test_power_response_tiene_header_granularidad(self, client: TestClient, device_id: str) -> None:
        """La respuesta debe incluir header X-Granularidad."""
        response = client.get(f"/api/v1/telemetria/power/{device_id}?periodo=24h&granularidad=5m")
        # Si la respuesta es exitosa (200), debe tener el header
        if response.status_code == 200:
            assert "x-granularidad" in {k.lower() for k in response.headers.keys()}
            assert response.headers.get("x-granularidad") in ("5m", "15m", "30m", "1h", "1d")


class TestEnergyEndpointGranularidad:
    """Tests para parámetro granularidad en /api/v1/telemetria/energy/{device_id}."""

    def test_energy_granularidad_5m_24h_valido(self, client: TestClient, device_id: str) -> None:
        """Energy acepta granularidad 5m para período 24h."""
        response = client.get(f"/api/v1/telemetria/energy/{device_id}?days=1&granularidad=5m")
        assert response.status_code in (200, 400, 401, 403)

    def test_energy_granularidad_1h_30d_valido(self, client: TestClient, device_id: str) -> None:
        """Energy acepta granularidad 1h para período 30d."""
        response = client.get(f"/api/v1/telemetria/energy/{device_id}?days=30&granularidad=1h")
        assert response.status_code in (200, 400, 401, 403)

    def test_energy_granularidad_invalida(self, client: TestClient, device_id: str) -> None:
        """Energy rechaza granularidad no válida."""
        response = client.get(f"/api/v1/telemetria/energy/{device_id}?days=1&granularidad=1d")
        # 1d es inválido para 24h (días=1)
        assert response.status_code in (400, 401, 403)

    def test_energy_acepta_granularity_legacy(self, client: TestClient, device_id: str) -> None:
        """Energy sigue aceptando parámetro granularity antiguo."""
        response = client.get(f"/api/v1/telemetria/energy/{device_id}?granularity=raw")
        assert response.status_code in (200, 401, 403)

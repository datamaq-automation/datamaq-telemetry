"""tests/unit/test_energy_ml_descubridor.py — Adaptador HTTP de energy-ml."""

import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from src.infrastructure.energy_ml.descubridor_http import EnergyMlHttpDescubridor

from src.domain.maquinas.exceptions import DescubridorNoDisponibleError

MEDIDOR_NAME = "Trafo arriba"


@pytest.fixture
def descubridor():
    return EnergyMlHttpDescubridor(base_url="http://127.0.0.1:8100", timeout_s=30)


def test_descubridor_convierte_kw_a_w_y_ausencia_de_dispersion_a_cero(descubridor):
    """JSON de energy-ml (kW) → MáquinaInferida (W); sin dispersion_kw → 0.0."""
    response_json = {
        "medidor": MEDIDOR_NAME,
        "maquinas": [
            {
                "potencia_kw": 92.0,
                "dispersion_kw": 5.0,
                "encendidos": 10,
                "apagados": 10,
                "ciclos_por_dia": 2.5,
                "on_off": True,
            },
            {
                "potencia_kw": 50.0,
                # dispersion_kw ausente
                "encendidos": 5,
                "apagados": 5,
                "ciclos_por_dia": 1.0,
                "on_off": True,
            },
        ],
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = Mock()
        mock_response.read.return_value = json.dumps(response_json).encode("utf-8")
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        desde = datetime(2026, 1, 1, tzinfo=timezone.utc)
        hasta = datetime(2026, 1, 2, tzinfo=timezone.utc)

        candidatas = descubridor.descubrir(MEDIDOR_NAME, desde, hasta)

    assert len(candidatas) == 2
    assert candidatas[0].potencia_w == 92000.0
    assert candidatas[0].dispersion_w == 5000.0
    assert candidatas[0].encendidos == 10
    assert candidatas[1].potencia_w == 50000.0
    assert candidatas[1].dispersion_w == 0.0  # Default a 0.0


def test_descubridor_http_200_pero_json_invalido_lanza_excepcion(descubridor):
    """HTTP 200 pero JSON inválido → DescubridorNoDisponibleError."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = Mock()
        mock_response.read.return_value = b"{ invalid json"
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        desde = datetime(2026, 1, 1, tzinfo=timezone.utc)
        hasta = datetime(2026, 1, 2, tzinfo=timezone.utc)

        with pytest.raises(DescubridorNoDisponibleError):
            descubridor.descubrir(MEDIDOR_NAME, desde, hasta)


def test_descubridor_http_500_lanza_excepcion(descubridor):
    """HTTP 500 → DescubridorNoDisponibleError."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = Exception("HTTP 500 Internal Server Error")

        desde = datetime(2026, 1, 1, tzinfo=timezone.utc)
        hasta = datetime(2026, 1, 2, tzinfo=timezone.utc)

        with pytest.raises(DescubridorNoDisponibleError):
            descubridor.descubrir(MEDIDOR_NAME, desde, hasta)


def test_descubridor_timeout_lanza_excepcion(descubridor):
    """Timeout en la conexión → DescubridorNoDisponibleError."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = TimeoutError("Connection timed out")

        desde = datetime(2026, 1, 1, tzinfo=timezone.utc)
        hasta = datetime(2026, 1, 2, tzinfo=timezone.utc)

        with pytest.raises(DescubridorNoDisponibleError):
            descubridor.descubrir(MEDIDOR_NAME, desde, hasta)


def test_descubridor_medidor_desconocido_devuelve_cargas_vacia(descubridor):
    """energy-ml devuelve maquinas=[] para medidor desconocido."""
    response_json = {"medidor": "Medidor desconocido", "maquinas": []}

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = Mock()
        mock_response.read.return_value = json.dumps(response_json).encode("utf-8")
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        desde = datetime(2026, 1, 1, tzinfo=timezone.utc)
        hasta = datetime(2026, 1, 2, tzinfo=timezone.utc)

        candidatas = descubridor.descubrir("Medidor desconocido", desde, hasta)

    assert candidatas == []


def test_descubridor_construye_url_correcta(descubridor):
    """Verifica que la URL se construya con los parámetros correctos."""
    response_json = {"medidor": MEDIDOR_NAME, "maquinas": []}

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = Mock()
        mock_response.read.return_value = json.dumps(response_json).encode("utf-8")
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        desde = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        hasta = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)

        descubridor.descubrir(MEDIDOR_NAME, desde, hasta)

        # Verificar que se llamó con la URL correcta
        call_args = mock_urlopen.call_args[0][0]
        assert isinstance(call_args, str)
        assert "medidor=Trafo+arriba" in call_args or "medidor=Trafo%20arriba" in call_args
        assert "desde=2026-01-01" in call_args
        assert "hasta=2026-01-02" in call_args

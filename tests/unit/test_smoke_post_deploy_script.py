"""tests/unit/test_smoke_post_deploy_script.py — Tests unitarios de scripts/smoke_post_deploy.py."""

import urllib.error
from unittest.mock import MagicMock, patch

from scripts.smoke_post_deploy import verificar_servicio


def test_verificar_servicio_exitoso_primer_intento():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"status": "ready", "database_conectada": true}'
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        ok = verificar_servicio("https://test.example.com/health/ready", max_intentos=1, espera_segundos=0)
        assert ok is True
        assert mock_urlopen.call_count == 1


def test_verificar_servicio_reintenta_si_not_ready():
    mock_not_ready = MagicMock()
    mock_not_ready.status = 200
    mock_not_ready.read.return_value = b'{"status": "not_ready", "database_conectada": false}'
    mock_not_ready.__enter__.return_value = mock_not_ready

    mock_ready = MagicMock()
    mock_ready.status = 200
    mock_ready.read.return_value = b'{"status": "ready", "database_conectada": true}'
    mock_ready.__enter__.return_value = mock_ready

    with patch("urllib.request.urlopen", side_effect=[mock_not_ready, mock_ready]) as mock_urlopen:
        ok = verificar_servicio("https://test.example.com/health/ready", max_intentos=2, espera_segundos=0)
        assert ok is True
        assert mock_urlopen.call_count == 2


def test_verificar_servicio_falla_si_persiste_error():
    err = urllib.error.URLError("Connection refused")
    with patch("urllib.request.urlopen", side_effect=err) as mock_urlopen:
        ok = verificar_servicio("https://test.example.com/health/ready", max_intentos=3, espera_segundos=0)
        assert ok is False
        assert mock_urlopen.call_count == 3

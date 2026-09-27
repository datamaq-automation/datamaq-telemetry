"""tests/integration/test_job_diagnostico_semanal.py — Tests Job Capa 3."""

from unittest.mock import MagicMock, patch

from scripts.job_diagnostico_semanal import JobDiagnosticoSemanal


def test_job_ejecuta_sin_errores():
    """Job ejecuta y retorna estructura esperada."""
    mock_app_service = MagicMock()
    mock_repo_dispositivos = MagicMock()
    mock_repo_telemetria = MagicMock()

    job = JobDiagnosticoSemanal(mock_app_service, mock_repo_dispositivos, mock_repo_telemetria)
    resultado = job.ejecutar()

    assert isinstance(resultado, dict)
    assert "dispositivos_procesados" in resultado
    assert "alertas_enviadas" in resultado
    assert "errores" in resultado


def test_job_alerta_si_score_alto():
    """Job cuenta alertas si score > 0.95."""
    mock_app_service = MagicMock()
    candidato = MagicMock(score=0.96)
    mock_app_service.ejecutar.return_value = MagicMock(candidatos=[candidato])

    mock_repo_dispositivos = MagicMock()
    mock_dispositivo = MagicMock(fases_con_ti="R,S,T")
    mock_repo_dispositivos.obtener_por_id.return_value = mock_dispositivo

    mock_repo_telemetria = MagicMock()

    job = JobDiagnosticoSemanal(mock_app_service, mock_repo_dispositivos, mock_repo_telemetria)

    with patch.object(job, "_obtener_dispositivos_con_anomalias", return_value=["dev-001"]):
        resultado = job.ejecutar()

    assert resultado["alertas_enviadas"] == 1
    assert resultado["dispositivos_procesados"] == 1

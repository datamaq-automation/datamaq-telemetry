"""tests/integration/test_job_diagnostico_semanal.py — Tests Job Capa 3."""

from unittest.mock import MagicMock

from scripts.job_diagnostico_semanal import JobDiagnosticoSemanal


def test_job_ejecuta_diagnostico_para_dispositivos_con_anomalias():
    """Job ejecuta diagnóstico para cada dispositivo con anomalías recientes."""
    mock_app_service = MagicMock()
    mock_app_service.ejecutar.return_value = MagicMock(candidatos=[], error=None)

    mock_repo_dispositivos = MagicMock()
    mock_dispositivo = MagicMock(fases_con_ti="R,S,T")
    mock_repo_dispositivos.obtener_por_id.return_value = mock_dispositivo

    mock_repo_telemetria = MagicMock()
    mock_repo_telemetria.db.execute.return_value.all.return_value = [("dev-001",), ("dev-002",)]

    job = JobDiagnosticoSemanal(mock_app_service, mock_repo_dispositivos, mock_repo_telemetria)
    resultado = job.ejecutar()

    assert resultado["dispositivos_procesados"] == 2
    assert mock_app_service.ejecutar.call_count == 2


def test_job_alerta_si_score_alto():
    """Job envía alerta si score > 0.95."""
    mock_app_service = MagicMock()
    candidato = MagicMock(score=0.96)
    mock_app_service.ejecutar.return_value = MagicMock(candidatos=[candidato])

    mock_repo_dispositivos = MagicMock()
    mock_dispositivo = MagicMock(fases_con_ti="R,S,T")
    mock_repo_dispositivos.obtener_por_id.return_value = mock_dispositivo

    mock_repo_telemetria = MagicMock()
    mock_repo_telemetria.db.execute.return_value.all.return_value = [("dev-001",)]

    job = JobDiagnosticoSemanal(mock_app_service, mock_repo_dispositivos, mock_repo_telemetria)
    resultado = job.ejecutar()

    assert resultado["alertas_enviadas"] == 1


def test_job_no_alerta_si_score_bajo():
    """Job NO envía alerta si score <= 0.95."""
    mock_app_service = MagicMock()
    candidato = MagicMock(score=0.90)
    mock_app_service.ejecutar.return_value = MagicMock(candidatos=[candidato])

    mock_repo_dispositivos = MagicMock()
    mock_dispositivo = MagicMock(fases_con_ti="R,S,T")
    mock_repo_dispositivos.obtener_por_id.return_value = mock_dispositivo

    mock_repo_telemetria = MagicMock()
    mock_repo_telemetria.db.execute.return_value.all.return_value = [("dev-001",)]

    job = JobDiagnosticoSemanal(mock_app_service, mock_repo_dispositivos, mock_repo_telemetria)
    resultado = job.ejecutar()

    assert resultado["alertas_enviadas"] == 0


def test_job_maneja_errores():
    """Job captura errores y continúa procesando."""
    mock_app_service = MagicMock()
    mock_app_service.ejecutar.side_effect = Exception("Error de diagnóstico")

    mock_repo_dispositivos = MagicMock()
    mock_dispositivo = MagicMock(fases_con_ti="R,S,T")
    mock_repo_dispositivos.obtener_por_id.return_value = mock_dispositivo

    mock_repo_telemetria = MagicMock()
    mock_repo_telemetria.db.execute.return_value.all.return_value = [("dev-001",)]

    job = JobDiagnosticoSemanal(mock_app_service, mock_repo_dispositivos, mock_repo_telemetria)
    resultado = job.ejecutar()

    assert resultado["dispositivos_procesados"] == 1
    assert len(resultado["errores"]) == 1
    assert "dev-001" in resultado["errores"][0]

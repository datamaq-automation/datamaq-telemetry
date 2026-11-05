"""tests/unit/test_deploy_workflows.py — Validación de puertos y fuentes de verdad en workflows de deploy."""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DEPLOY_YML = RAIZ / ".github" / "workflows" / "deploy.yml"
DEPLOY_STAGING_YML = RAIZ / ".github" / "workflows" / "deploy-staging.yml"
CI_YML = RAIZ / ".github" / "workflows" / "ci.yml"
CI_NIGHTLY_YML = RAIZ / ".github" / "workflows" / "ci-nightly.yml"


def _bloque_on(ruta: Path) -> str:
    """Devuelve el bloque `on:` del workflow (hasta `jobs:`), que define sus disparadores."""
    contenido = ruta.read_text(encoding="utf-8")
    return contenido.split("jobs:", 1)[0]


def _extraer_health_url_deploy_yml() -> str | None:
    """Extrae la URL de health check de producción configurada en deploy.yml."""
    contenido = DEPLOY_YML.read_text(encoding="utf-8")
    match = re.search(r'echo\s+"health_url=(https?://[^"\s]+)"\s+>>\s+"\$GITHUB_OUTPUT"', contenido)
    return match.group(1) if match else None


def _extraer_health_url_deploy_staging_yml() -> str | None:
    """Extrae DEPLOY_HEALTH_URL configurada en deploy-staging.yml."""
    contenido = DEPLOY_STAGING_YML.read_text(encoding="utf-8")
    match = re.search(r"DEPLOY_HEALTH_URL:\s*(https?://[^\s]+)", contenido)
    return match.group(1) if match else None


def test_deploy_yml_solo_produccion_puerto_8885():
    """deploy.yml despliega solo producción (8885); staging vive en deploy-staging.yml."""
    assert DEPLOY_YML.exists(), "Falta .github/workflows/deploy.yml"
    url = _extraer_health_url_deploy_yml()

    assert url is not None, "No se encontró health_url en deploy.yml"
    assert ":8885/" in url, f"Producción en deploy.yml debe usar puerto 8885, se encontró: {url}"
    assert url == "http://localhost:8885/health/ready"
    assert ":8000" not in url, "Producción en deploy.yml tiene residuo de puerto 8000"

    contenido = DEPLOY_YML.read_text(encoding="utf-8")
    assert ":8886/" not in contenido, "deploy.yml no debe definir el puerto de staging (va en deploy-staging.yml)"
    assert "workflow_run" not in contenido, "deploy.yml ya no debe depender de workflow_run"


def test_deploy_yml_se_dispara_solo_con_push_a_main_o_manual():
    """Decisión 2026-10-27: producción se despliega con push a main o workflow_dispatch."""
    bloque_on = _bloque_on(DEPLOY_YML)

    assert "push:" in bloque_on
    assert "branches: [main]" in bloque_on
    assert "workflow_dispatch:" in bloque_on
    assert "workflow_run" not in bloque_on


def test_deploy_staging_yml_puerto_8886():
    """deploy-staging.yml debe tener DEPLOY_HEALTH_URL con puerto 8886."""
    assert DEPLOY_STAGING_YML.exists(), "Falta .github/workflows/deploy-staging.yml"
    url = _extraer_health_url_deploy_staging_yml()

    assert url is not None, "No se encontró DEPLOY_HEALTH_URL en deploy-staging.yml"
    assert ":8886/" in url, f"deploy-staging.yml debe usar puerto 8886, se encontró: {url}"
    assert url == "http://localhost:8886/health/ready"


def test_smoke_post_deploy_urls_publicas_en_workflows():
    """Ambos workflows deben ejecutar smoke tests contra las URLs públicas oficiales."""
    contenido_prod = DEPLOY_YML.read_text(encoding="utf-8")
    contenido_staging = DEPLOY_STAGING_YML.read_text(encoding="utf-8")

    assert "https://api.datamaq.com.ar/health/ready" in contenido_prod
    assert "https://api-dev.datamaq.com.ar/health/ready" in contenido_prod
    assert "https://api-dev.datamaq.com.ar/health/ready" in contenido_staging
    assert "scripts/smoke_post_deploy.py" in contenido_prod
    assert "scripts/smoke_post_deploy.py" in contenido_staging


def test_ci_yml_solo_corre_en_pr_a_main():
    """Decisión 2026-10-27: el CI en la nube corre solo en el PR hacia main."""
    bloque_on = _bloque_on(CI_YML)

    assert "pull_request:" in bloque_on
    assert "branches: [main]" in bloque_on
    assert "push:" not in bloque_on


def test_workflows_manuales_sin_schedule_ni_push_a_develop():
    """Staging y nightly se disparan a mano: sin schedule y sin push a develop."""
    for ruta in (DEPLOY_STAGING_YML, CI_NIGHTLY_YML):
        bloque_on = _bloque_on(ruta)
        assert "workflow_dispatch:" in bloque_on, f"{ruta.name} debe ser manual"
        assert "schedule:" not in bloque_on, f"{ruta.name} no debe tener schedule"
        assert "push:" not in bloque_on, f"{ruta.name} no debe dispararse con push"

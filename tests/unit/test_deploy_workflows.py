"""tests/unit/test_deploy_workflows.py — Validación de puertos y fuentes de verdad en workflows de deploy."""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DEPLOY_YML = RAIZ / ".github" / "workflows" / "deploy.yml"
DEPLOY_STAGING_YML = RAIZ / ".github" / "workflows" / "deploy-staging.yml"


def _extraer_health_url_deploy_yml() -> dict[str, str]:
    """Extrae las URLs de health check configuradas para staging y producción en deploy.yml."""
    contenido = DEPLOY_YML.read_text(encoding="utf-8")
    urls = {}

    # Bloque staging
    match_staging = re.search(
        r'if\s+\[\s+"\$BRANCH"\s+=\s+"develop"\s+\];.*?'
        r'echo\s+"health_url=(https?://[^"\s]+)"\s+>>\s+"\$GITHUB_OUTPUT"',
        contenido,
        re.DOTALL,
    )
    if match_staging:
        urls["staging"] = match_staging.group(1)

    # Bloque production
    match_prod = re.search(
        r'elif\s+\[\s+"\$BRANCH"\s+=\s+"main"\s+\];.*?'
        r'echo\s+"health_url=(https?://[^"\s]+)"\s+>>\s+"\$GITHUB_OUTPUT"',
        contenido,
        re.DOTALL,
    )
    if match_prod:
        urls["production"] = match_prod.group(1)

    return urls


def _extraer_health_url_deploy_staging_yml() -> str | None:
    """Extrae DEPLOY_HEALTH_URL configurada en deploy-staging.yml."""
    contenido = DEPLOY_STAGING_YML.read_text(encoding="utf-8")
    match = re.search(r"DEPLOY_HEALTH_URL:\s*(https?://[^\s]+)", contenido)
    return match.group(1) if match else None


def test_deploy_yml_puertos_staging_y_produccion():
    """deploy.yml debe usar puerto 8886 para staging y 8885 para producción."""
    assert DEPLOY_YML.exists(), "Falta .github/workflows/deploy.yml"
    urls = _extraer_health_url_deploy_yml()

    assert "staging" in urls, "No se encontró health_url de staging en deploy.yml"
    assert "production" in urls, "No se encontró health_url de producción en deploy.yml"

    # Staging debe ser 8886
    assert ":8886/" in urls["staging"], f"Staging en deploy.yml debe usar puerto 8886, se encontró: {urls['staging']}"
    assert urls["staging"] == "http://localhost:8886/health/ready"

    # Producción debe ser 8885 (NO 8000)
    assert ":8885/" in urls["production"], (
        f"Producción en deploy.yml debe usar puerto 8885, se encontró: {urls['production']}"
    )
    assert urls["production"] == "http://localhost:8885/health/ready"
    assert ":8000" not in urls["production"], "Producción en deploy.yml tiene residuo de puerto 8000"


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

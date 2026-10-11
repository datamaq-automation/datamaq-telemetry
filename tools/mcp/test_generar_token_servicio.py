"""tools/mcp/test_generar_token_servicio.py — Pruebas unitarias para el generador de tokens de servicio."""

import io
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.settings.config import get_settings
from tools.mcp.generar_token_servicio import (
    construir_instrucciones,
    generar_token_servicio,
    main,
)


def test_generar_token_servicio_por_defecto():
    """Valida la generación de token con parámetros por defecto (365 días, mcp_service, superadmin)."""
    token = generar_token_servicio()
    assert isinstance(token, str)
    assert len(token.split(".")) == 3

    settings = get_settings()
    token_service = JwtTokenService(settings.API_SECRET_KEY)
    claims = token_service.verificar(token)

    assert claims is not None
    assert claims["usuario"] == "mcp_service"
    assert claims["rol"] == "superadmin"
    assert "sub" in claims

    ahora_ts = int(datetime.now(timezone.utc).timestamp())
    assert claims["exp"] > ahora_ts + (364 * 86400)


def test_generar_token_servicio_argumentos_personalizados():
    """Valida la generación con parámetros custom de usuario, rol y organización."""
    token = generar_token_servicio(
        dias=10,
        usuario="admin_externo",
        rol="administrador",
        organizacion_id="org_alpha",
        usuario_id="uuid-fijo-123",
    )

    settings = get_settings()
    claims = JwtTokenService(settings.API_SECRET_KEY).verificar(token)
    assert claims is not None
    assert claims["usuario"] == "admin_externo"
    assert claims["rol"] == "administrador"
    assert claims["org"] == "org_alpha"
    assert claims["sub"] == "uuid-fijo-123"


def test_generar_token_servicio_dias_invalidos():
    """Valida que días <= 0 levante ValueError."""
    with pytest.raises(ValueError, match="El parámetro dias debe ser un entero positivo"):
        generar_token_servicio(dias=0)

    with pytest.raises(ValueError, match="El parámetro dias debe ser un entero positivo"):
        generar_token_servicio(dias=-10)


def test_construir_instrucciones_formato():
    """Valida que el texto generado incluya las variables para .env y la configuración de Claude Desktop."""
    token_fake = "eyJhbGciOiJIUzI1NiJ9.fake.signature"
    texto = construir_instrucciones(token_fake, "usuario_demo", "superadmin", 90)

    assert f"DATAMAQ_AUTH_TOKEN={token_fake}" in texto
    assert "claude_desktop_config.json" in texto
    assert '"DATAMAQ_API_URL": "https://api.datamaq.com.ar"' in texto
    assert f'"DATAMAQ_AUTH_TOKEN": "{token_fake}"' in texto


def test_main_cli_solo_token():
    """Valida la opción CLI --solo-token para pipes y automatizaciones."""
    f = io.StringIO()
    with patch("sys.stdout", f):
        codigo = main(["--dias", "15", "--usuario", "ci_worker", "--solo-token"])

    assert codigo == 0
    token_impreso = f.getvalue().strip()
    assert len(token_impreso.split(".")) == 3

    claims = JwtTokenService(get_settings().API_SECRET_KEY).verificar(token_impreso)
    assert claims is not None
    assert claims["usuario"] == "ci_worker"


def test_main_cli_instrucciones_completas():
    """Valida que la ejecución normal de CLI imprima las instrucciones completas."""
    f = io.StringIO()
    with patch("sys.stdout", f):
        codigo = main(["--dias", "45", "--usuario", "mcp_desktop", "--rol", "operador"])

    assert codigo == 0
    salida = f.getvalue()
    assert "TOKEN JWT DE SERVICIO GENERADO EXITOSAMENTE" in salida
    assert "DATAMAQ_AUTH_TOKEN=" in salida
    assert "mcpServers" in salida


def test_main_cli_error_retorna_codigo_uno():
    """Valida que errores de validación impriman en stderr y retornen código 1."""
    f_err = io.StringIO()
    with patch("sys.stderr", f_err):
        codigo = main(["--dias", "-5"])

    assert codigo == 1
    assert "Error generando token de servicio" in f_err.getvalue()

"""tests/unit/test_frontend_url_default.py — El enlace de recuperación no apunta a www (Issue #106).

La página /restablecer-contrasena es de la app, no del sitio público www. Con el default anterior el correo
traía un enlace que no funcionaba. Este test fija el default del settings y el del caso de uso.
"""

from src.application.use_cases.recuperar_contrasena import SolicitarRecuperacionContrasenaUseCase
from src.infrastructure.settings.config import Settings

FRONTEND_URL_APP = "https://app.datamaq.com.ar"


def test_settings_frontend_url_por_defecto_apunta_a_la_app(monkeypatch):
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    settings = Settings(_env_file=None, APP_ENV="development", DEBUG=True)
    assert settings.FRONTEND_URL == FRONTEND_URL_APP


def test_caso_de_uso_frontend_url_por_defecto_apunta_a_la_app():
    caso = SolicitarRecuperacionContrasenaUseCase(
        repositorio_usuarios=None,
        generador_token=None,
        servicio_email=None,
    )
    assert caso.frontend_url == FRONTEND_URL_APP

"""tests/unit/test_errores_sin_detalle_tecnico.py — Las respuestas 500 no filtran detalle técnico.

El texto técnico (excepción, nombre de variable, nombre de header) va al log con exc_info, no al body.
"""

from fastapi.testclient import TestClient

from src.infrastructure.fastapi.dependencies import (
    get_consultar_analitica_planta_use_case,
    get_monitorear_potencia_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.planta_ownership import resolver_planta_permitida
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import get_settings

_SECRETO = "detalle-interno-no-debe-filtrarse"
_GENERICO = "Ocurrió un error interno en el servidor"


def _cliente(overrides: dict) -> TestClient:
    app = create_app(get_settings())
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "user_id": "u-1",
        "organizacion_id": "org-garin",
        "sub": "u-1",
    }
    app.dependency_overrides[resolver_planta_permitida] = lambda planta_id=None: planta_id
    app.dependency_overrides.update(overrides)
    return TestClient(app)


class _NotificadorRoto:
    async def ejecutar(self, planta_id: str) -> None:
        raise RuntimeError(_SECRETO)


class _AnaliticaRota:
    def obtener_banco_capacitores(self, **_: object) -> None:
        raise RuntimeError(_SECRETO)

    def obtener_penalizaciones(self, **_: object) -> None:
        raise RuntimeError(_SECRETO)


def test_notificador_sin_use_case_responde_500_generico():
    client = _cliente({get_monitorear_potencia_use_case: lambda: None})

    r = client.get("/api/v1/tuya/notificador/estado?planta_id=planta-garin")

    assert r.status_code == 500
    assert r.json()["detail"] == _GENERICO
    assert "Use case" not in r.text


def test_notificador_excepcion_responde_500_generico_sin_filtrar():
    client = _cliente({get_monitorear_potencia_use_case: lambda: _NotificadorRoto()})

    r = client.get("/api/v1/tuya/notificador/estado?planta_id=planta-garin")

    assert r.status_code == 500
    assert r.json()["detail"] == _GENERICO
    assert _SECRETO not in r.text


def test_analitica_banco_sin_use_case_responde_500_generico():
    client = _cliente({get_consultar_analitica_planta_use_case: lambda: None})

    r = client.get("/api/v1/analitica/banco-capacitores/planta?planta_id=planta-garin")

    assert r.status_code == 500
    assert r.json()["detail"] == _GENERICO
    assert "Use case" not in r.text


def test_analitica_banco_excepcion_responde_500_generico_sin_filtrar():
    client = _cliente({get_consultar_analitica_planta_use_case: lambda: _AnaliticaRota()})

    r = client.get("/api/v1/analitica/banco-capacitores/planta?planta_id=planta-garin")

    assert r.status_code == 500
    assert r.json()["detail"] == _GENERICO
    assert _SECRETO not in r.text


def test_analitica_penalizaciones_sin_use_case_responde_500_generico():
    client = _cliente({get_consultar_analitica_planta_use_case: lambda: None})

    r = client.get("/api/v1/analitica/penalizaciones/planta?planta_id=planta-garin")

    assert r.status_code == 500
    assert r.json()["detail"] == _GENERICO
    assert "Use case" not in r.text


def test_analitica_penalizaciones_excepcion_responde_500_generico_sin_filtrar():
    client = _cliente({get_consultar_analitica_planta_use_case: lambda: _AnaliticaRota()})

    r = client.get("/api/v1/analitica/penalizaciones/planta?planta_id=planta-garin")

    assert r.status_code == 500
    assert r.json()["detail"] == _GENERICO
    assert _SECRETO not in r.text


def test_cambio_contrasena_sin_otp_responde_503_con_codigo_sin_sufijo():
    import pytest
    from fastapi import HTTPException

    from src.infrastructure.fastapi.dependencies_cambio_contrasena import get_clave_otp
    from src.infrastructure.settings.config import Settings

    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        DEBUG=False,
        API_SECRET_KEY="secreto-fuerte-123456",
        DB_PASSWORD="clave-segura",
        OTP_HMAC_KEY="",
    )

    with pytest.raises(HTTPException) as exc:
        get_clave_otp(settings)

    assert exc.value.status_code == 503
    assert exc.value.detail == "cambio_contrasena_no_disponible"
    assert "OTP_HMAC_KEY" not in str(exc.value.detail)

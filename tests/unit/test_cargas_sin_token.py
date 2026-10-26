"""tests/unit/test_cargas_sin_token.py — Las lecturas de cargas exigen token válido (#39).

Con el usuario invitado eliminado, la única vía sin credenciales era `POST /api/auth/guest`.
Este test fija que las lecturas de cargas responden 401 sin token, con la configuración por defecto
(AUTH_REQUIRED=True), sin usar overrides de autenticación.
"""

from fastapi.testclient import TestClient

from src.infrastructure.fastapi.server import create_app

RUTAS_DE_LECTURA = [
    "/api/v1/cargas",
    "/api/v1/cargas/atribucion?device_id=dispositivo-1",
    "/api/v1/cargas/perfil?device_id=dispositivo-1",
    "/api/v1/cargas/presets?device_id=dispositivo-1",
    "/api/v1/cargas/intervalos?device_id=dispositivo-1",
    "/api/v1/cargas/exportar/csv",
]


def test_lecturas_de_cargas_responden_401_sin_token():
    client = TestClient(create_app())

    for ruta in RUTAS_DE_LECTURA:
        resp = client.get(ruta)
        assert resp.status_code == 401, f"{ruta} respondió {resp.status_code} sin token"

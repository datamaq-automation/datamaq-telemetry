"""tests/unit/test_auth_router.py — Tests unitarios para las rutas de autenticación."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi import Response
from fastapi.testclient import TestClient

from src.application.dtos.auth_dto import (
    Activar2FARequestDTO,
    Desactivar2FARequestDTO,
    LoginRequestDTO,
    LoginResponseDTO,
    MeResponseDTO,
    Operacion2FAResponseDTO,
    RestablecerContrasenaDTO,
    Setup2FAResponseDTO,
    SolicitarRecuperacionDTO,
    Verificar2FARequestDTO,
)
from src.domain.auth.exceptions import (
    Codigo2FAInvalidoError,
    ContrasenaDebilError,
    CredencialesInvalidasError,
    DemasiadosIntentosError,
    Setup2FAInvalidoError,
    TokenMFAPendienteInvalidoError,
    TokenRecuperacionInvalidoError,
    UsuarioInactivoError,
)
from src.infrastructure.fastapi.auth_dependencies import (
    get_activar_2fa_use_case,
    get_auth_use_case,
    get_desactivar_2fa_use_case,
    get_revocar_dispositivos_use_case,
    get_setup_2fa_use_case,
    get_verificar_2fa_use_case,
)
from src.infrastructure.fastapi.dependencies import (
    get_restablecer_contrasena_use_case,
    get_settings_dep,
    get_solicitar_recuperacion_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.routes.auth_router import (
    DEVICE_TRUST_COOKIE,
    DEVICE_TRUST_MAX_AGE,
    _fijar_cookie,
    _fijar_cookie_dispositivo,
    _obtener_ip_cliente,
)
from src.infrastructure.fastapi.routes.auth_router import (
    solicitar_recuperacion as solicitar_recuperacion_handler,
)
from src.infrastructure.fastapi.routes.auth_router import (
    verificar_2fa as verificar_2fa_handler,
)
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import Settings

AHORA = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def _cliente(
    claims: dict | None = None,
    settings: Settings | None = None,
) -> tuple[TestClient, dict[str, MagicMock]]:
    app = create_app(settings=settings)
    mocks = {
        "auth": MagicMock(),
        "verificar_2fa": MagicMock(),
        "setup_2fa": MagicMock(),
        "activar_2fa": MagicMock(),
        "desactivar_2fa": MagicMock(),
        "solicitar_recuperacion": MagicMock(),
        "restablecer_contrasena": MagicMock(),
        "revocar_dispositivos": MagicMock(),
    }
    app.dependency_overrides[get_auth_use_case] = lambda: mocks["auth"]
    app.dependency_overrides[get_verificar_2fa_use_case] = lambda: mocks["verificar_2fa"]
    app.dependency_overrides[get_setup_2fa_use_case] = lambda: mocks["setup_2fa"]
    app.dependency_overrides[get_activar_2fa_use_case] = lambda: mocks["activar_2fa"]
    app.dependency_overrides[get_desactivar_2fa_use_case] = lambda: mocks["desactivar_2fa"]
    app.dependency_overrides[get_solicitar_recuperacion_use_case] = lambda: mocks["solicitar_recuperacion"]
    app.dependency_overrides[get_restablecer_contrasena_use_case] = lambda: mocks["restablecer_contrasena"]
    app.dependency_overrides[get_revocar_dispositivos_use_case] = lambda: mocks["revocar_dispositivos"]

    if claims is not None:
        app.dependency_overrides[get_usuario_actual] = lambda: claims
    else:
        app.dependency_overrides[get_usuario_actual] = lambda: {
            "sub": "user-uuid-default",
            "usuario": "admin@planta.local",
            "rol": "admin",
        }

    if settings is not None:
        app.dependency_overrides[get_settings_dep] = lambda: settings

    return TestClient(app), mocks


# ==============================================================================
# 1. HELPERS INTERNOS
# ==============================================================================


def test_fijar_cookie():
    response = Response()
    settings = Settings(
        AUTH_COOKIE_NOMBRE="custom_session",
        AUTH_COOKIE_HTTPONLY=True,
        AUTH_COOKIE_SAMESITE="lax",
    )
    _fijar_cookie(response, settings, "token-prueba")

    cookie_header = response.headers.get("set-cookie", "")
    assert "custom_session=token-prueba" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=lax" in cookie_header


def test_fijar_cookie_dispositivo():
    response = Response()
    settings = Settings(
        AUTH_COOKIE_SAMESITE="lax",
    )
    _fijar_cookie_dispositivo(response, settings, "trust-token-123")

    cookie_header = response.headers.get("set-cookie", "")
    assert f"{DEVICE_TRUST_COOKIE}=trust-token-123" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=lax" in cookie_header
    assert f"Max-Age={DEVICE_TRUST_MAX_AGE}" in cookie_header
    assert "Path=/api/v1/auth" in cookie_header


def test_obtener_ip_cliente_none():
    assert _obtener_ip_cliente(None) == "desconocida"


def test_obtener_ip_cliente_x_forwarded_for():
    request = MagicMock()
    request.headers = {"X-Forwarded-For": "203.0.113.195, 70.41.3.18, 150.172.238.178"}
    assert _obtener_ip_cliente(request) == "203.0.113.195"


def test_obtener_ip_cliente_sin_x_forwarded_for_usa_client_host():
    request = MagicMock()
    request.headers = {}
    request.client.host = "192.168.1.100"
    assert _obtener_ip_cliente(request) == "192.168.1.100"


def test_obtener_ip_cliente_sin_client():
    request = MagicMock()
    request.headers = {}
    request.client = None
    assert _obtener_ip_cliente(request) == "desconocida"


# ==============================================================================
# 2. LOGIN
# ==============================================================================


def test_login_exitoso_con_token_fija_cookie():
    client, mocks = _cliente()
    mocks["auth"].login.return_value = LoginResponseDTO(
        token="jwt-access-token",
        expira_en=AHORA,
        require_2fa=False,
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"usuario": "admin", "contrasena": "clave123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token"] == "jwt-access-token"
    assert data["require_2fa"] is False
    assert "datamaq_token" in response.cookies
    assert response.cookies["datamaq_token"] == "jwt-access-token"


def test_login_con_device_trust_cookie_y_x_forwarded_for():
    client, mocks = _cliente()
    client.cookies.set(DEVICE_TRUST_COOKIE, "device-trust-token-abc")
    mocks["auth"].login.return_value = LoginResponseDTO(
        token="jwt-access-token",
        expira_en=AHORA,
        require_2fa=False,
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"usuario": "admin", "contrasena": "clave123"},
        headers={"X-Forwarded-For": "203.0.113.50, 10.0.0.1"},
    )
    assert response.status_code == 200
    mocks["auth"].login.assert_called_once()
    call_args, call_kwargs = mocks["auth"].login.call_args
    assert isinstance(call_args[0], LoginRequestDTO)
    assert call_args[0].usuario == "admin"
    assert call_kwargs["device_token"] == "device-trust-token-abc"
    assert call_kwargs["clave_ip"] == "203.0.113.50"
    assert call_kwargs["ip_origen"] == "203.0.113.50"


def test_login_requiere_2fa_no_fija_cookie():
    client, mocks = _cliente()
    mocks["auth"].login.return_value = LoginResponseDTO(
        token=None,
        expira_en=AHORA,
        require_2fa=True,
        mfa_token="mfa-pending-token",
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"usuario": "admin", "contrasena": "clave123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token"] is None
    assert data["require_2fa"] is True
    assert data["mfa_token"] == "mfa-pending-token"
    assert "datamaq_token" not in response.cookies


def test_login_credenciales_invalidas():
    client, mocks = _cliente()
    mocks["auth"].login.side_effect = CredencialesInvalidasError("credenciales_invalidas")

    response = client.post(
        "/api/v1/auth/login",
        json={"usuario": "admin", "contrasena": "clave_erronea"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "credenciales_invalidas"


def test_login_demasiados_intentos():
    client, mocks = _cliente()
    mocks["auth"].login.side_effect = DemasiadosIntentosError("demasiados_intentos", retry_after_seg=45)

    response = client.post(
        "/api/v1/auth/login",
        json={"usuario": "admin", "contrasena": "clave123"},
    )
    assert response.status_code == 429
    assert response.json()["detail"] == "demasiados_intentos"
    assert response.headers.get("Retry-After") == "45"


def test_login_usuario_inactivo():
    client, mocks = _cliente()
    mocks["auth"].login.side_effect = UsuarioInactivoError("usuario_inactivo")

    response = client.post(
        "/api/v1/auth/login",
        json={"usuario": "inactivo", "contrasena": "clave123"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "usuario_inactivo"


# ==============================================================================
# 4. LOGOUT
# ==============================================================================


def test_logout_elimina_cookie():
    client, _ = _cliente()
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"detail": "sesion_cerrada"}

    cookie_header = response.headers.get("set-cookie", "")
    assert "datamaq_token=" in cookie_header
    assert "max-age=0" in cookie_header.lower() or "expires=" in cookie_header.lower()


# ==============================================================================
# 5. ME
# ==============================================================================


def test_me_exitoso():
    claims = {"usuario": "admin@planta.local", "rol": "admin", "sub": "u-123"}
    client, mocks = _cliente(claims=claims)
    mocks["auth"].me.return_value = MeResponseDTO(
        usuario="admin@planta.local",
        rol="admin",
        totp_enabled=True,
        organizacion_id="org-uuid-1",
        organizacion_nombre="Planta Central",
    )

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["usuario"] == "admin@planta.local"
    assert data["rol"] == "admin"
    assert data["totp_enabled"] is True
    assert data["organizacion_id"] == "org-uuid-1"
    assert data["organizacion_nombre"] == "Planta Central"
    mocks["auth"].me.assert_called_once_with(claims)


def test_me_error_token_invalido():
    client, mocks = _cliente()
    mocks["auth"].me.side_effect = CredencialesInvalidasError("credenciales_invalidas")

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "credenciales_invalidas"


# ==============================================================================
# 6. 2FA: VERIFICAR
# ==============================================================================


def test_verificar_2fa_con_device_trust():
    client, mocks = _cliente()
    mocks["verificar_2fa"].verificar.return_value = LoginResponseDTO(
        token="jwt-verified-token",
        expira_en=AHORA,
        require_2fa=False,
        device_trust_token="new-device-trust-token",
    )

    response = client.post(
        "/api/v1/auth/2fa/verificar",
        json={
            "mfa_token": "mfa-token-xyz",
            "codigo": "123456",
            "recordar_dispositivo": True,
        },
        headers={
            "User-Agent": "DatamaqMobile/1.0",
            "X-Forwarded-For": "198.51.100.12, 10.0.0.1",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token"] == "jwt-verified-token"
    assert "datamaq_token" in response.cookies
    assert response.cookies["datamaq_token"] == "jwt-verified-token"

    cookie_header = response.headers.get("set-cookie", "")
    assert f"{DEVICE_TRUST_COOKIE}=new-device-trust-token" in cookie_header
    assert "Path=/api/v1/auth" in cookie_header

    mocks["verificar_2fa"].verificar.assert_called_once()
    call_args, call_kwargs = mocks["verificar_2fa"].verificar.call_args
    assert isinstance(call_args[0], Verificar2FARequestDTO)
    assert call_args[0].codigo == "123456"
    assert call_kwargs["ip_origen"] == "198.51.100.12"
    assert call_kwargs["user_agent"] == "DatamaqMobile/1.0"


def test_verificar_2fa_sin_device_trust():
    client, mocks = _cliente()
    mocks["verificar_2fa"].verificar.return_value = LoginResponseDTO(
        token="jwt-verified-token",
        expira_en=AHORA,
        require_2fa=False,
        device_trust_token=None,
    )

    response = client.post(
        "/api/v1/auth/2fa/verificar",
        json={
            "mfa_token": "mfa-token-xyz",
            "codigo": "123456",
            "recordar_dispositivo": False,
        },
    )
    assert response.status_code == 200
    assert "datamaq_token" in response.cookies
    cookie_header = response.headers.get("set-cookie", "")
    assert DEVICE_TRUST_COOKIE not in cookie_header


def test_verificar_2fa_codigo_invalido():
    client, mocks = _cliente()
    mocks["verificar_2fa"].verificar.side_effect = Codigo2FAInvalidoError("codigo_2fa_invalido")

    response = client.post(
        "/api/v1/auth/2fa/verificar",
        json={
            "mfa_token": "mfa-token-xyz",
            "codigo": "000000",
            "recordar_dispositivo": False,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "codigo_2fa_invalido"


def test_verificar_2fa_token_mfa_invalido():
    client, mocks = _cliente()
    mocks["verificar_2fa"].verificar.side_effect = TokenMFAPendienteInvalidoError("token_mfa_invalido")

    response = client.post(
        "/api/v1/auth/2fa/verificar",
        json={
            "mfa_token": "mfa-expirado",
            "codigo": "123456",
            "recordar_dispositivo": False,
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "token_mfa_invalido"


def test_verificar_2fa_request_none_directo():
    response = Response()
    settings = Settings()
    mock_uc = MagicMock()
    mock_uc.verificar.return_value = LoginResponseDTO(
        token="direct-jwt",
        expira_en=AHORA,
        require_2fa=False,
    )
    dto = Verificar2FARequestDTO(mfa_token="mfa-direct", codigo="123456")
    res = verificar_2fa_handler(dto, mock_uc, response, settings, request=None)
    assert res.token == "direct-jwt"
    mock_uc.verificar.assert_called_once_with(dto, ip_origen="desconocida", user_agent="")


# ==============================================================================
# 7. 2FA: SETUP
# ==============================================================================


def test_setup_2fa_con_usuario_en_claims():
    client, mocks = _cliente(claims={"usuario": "alice", "sub": "u-alice"})
    mocks["setup_2fa"].ejecutar.return_value = Setup2FAResponseDTO(
        secret="JBSWY3DPEHPK3PXP",
        uri="otpauth://totp/Datamaq:alice?secret=JBSWY3DPEHPK3PXP",
        qr_svg="<svg>qr</svg>",
        backup_codes=["b1", "b2", "b3"],
    )

    response = client.post("/api/v1/auth/2fa/setup")
    assert response.status_code == 200
    data = response.json()
    assert data["secret"] == "JBSWY3DPEHPK3PXP"
    assert data["uri"].startswith("otpauth://totp/Datamaq:alice")
    assert data["qr_svg"] == "<svg>qr</svg>"
    assert data["backup_codes"] == ["b1", "b2", "b3"]
    mocks["setup_2fa"].ejecutar.assert_called_once_with("alice")


def test_setup_2fa_con_sub_fallback():
    client, mocks = _cliente(claims={"sub": "user-fallback-sub"})
    mocks["setup_2fa"].ejecutar.return_value = Setup2FAResponseDTO(
        secret="JBSWY3DPEHPK3PXP",
        uri="otpauth://totp/Datamaq:user-fallback-sub?secret=JBSWY3DPEHPK3PXP",
        qr_svg="<svg>qr</svg>",
        backup_codes=["b1"],
    )

    response = client.post("/api/v1/auth/2fa/setup")
    assert response.status_code == 200
    mocks["setup_2fa"].ejecutar.assert_called_once_with("user-fallback-sub")


def test_setup_2fa_error():
    client, mocks = _cliente()
    mocks["setup_2fa"].ejecutar.side_effect = Setup2FAInvalidoError("setup_2fa_invalido")

    response = client.post("/api/v1/auth/2fa/setup")
    assert response.status_code == 400
    assert response.json()["detail"] == "setup_2fa_invalido"


# ==============================================================================
# 8. 2FA: ACTIVAR
# ==============================================================================


def test_activar_2fa_con_usuario_en_claims():
    client, mocks = _cliente(claims={"usuario": "bob", "sub": "u-bob"})
    mocks["activar_2fa"].ejecutar.return_value = Operacion2FAResponseDTO(
        exito=True,
        mensaje="2fa_activado",
    )

    response = client.post(
        "/api/v1/auth/2fa/activar",
        json={
            "secret": "JBSWY3DPEHPK3PXP1234",
            "codigo": "123456",
            "backup_codes": ["code1", "code2"],
        },
    )
    assert response.status_code == 200
    assert response.json() == {"exito": True, "mensaje": "2fa_activado"}
    mocks["activar_2fa"].ejecutar.assert_called_once()
    call_args, _ = mocks["activar_2fa"].ejecutar.call_args
    assert call_args[0] == "bob"
    assert isinstance(call_args[1], Activar2FARequestDTO)
    assert call_args[1].codigo == "123456"


def test_activar_2fa_con_sub_fallback():
    client, mocks = _cliente(claims={"sub": "sub-bob-fallback"})
    mocks["activar_2fa"].ejecutar.return_value = Operacion2FAResponseDTO(
        exito=True,
        mensaje="2fa_activado",
    )

    response = client.post(
        "/api/v1/auth/2fa/activar",
        json={
            "secret": "JBSWY3DPEHPK3PXP1234",
            "codigo": "123456",
            "backup_codes": ["code1"],
        },
    )
    assert response.status_code == 200
    mocks["activar_2fa"].ejecutar.assert_called_once()
    call_args, _ = mocks["activar_2fa"].ejecutar.call_args
    assert call_args[0] == "sub-bob-fallback"


def test_activar_2fa_codigo_invalido():
    client, mocks = _cliente()
    mocks["activar_2fa"].ejecutar.side_effect = Codigo2FAInvalidoError("codigo_2fa_invalido")

    response = client.post(
        "/api/v1/auth/2fa/activar",
        json={
            "secret": "JBSWY3DPEHPK3PXP1234",
            "codigo": "000000",
            "backup_codes": ["code1"],
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "codigo_2fa_invalido"


# ==============================================================================
# 9. 2FA: DESACTIVAR
# ==============================================================================


def test_desactivar_2fa_con_usuario_en_claims():
    client, mocks = _cliente(claims={"usuario": "clara", "sub": "u-clara"})
    mocks["desactivar_2fa"].ejecutar.return_value = Operacion2FAResponseDTO(
        exito=True,
        mensaje="2fa_desactivado",
    )

    response = client.post(
        "/api/v1/auth/2fa/desactivar",
        json={"contrasena": "ClaveSegura123!", "codigo": "123456"},
    )
    assert response.status_code == 200
    assert response.json() == {"exito": True, "mensaje": "2fa_desactivado"}
    mocks["desactivar_2fa"].ejecutar.assert_called_once()
    call_args, _ = mocks["desactivar_2fa"].ejecutar.call_args
    assert call_args[0] == "clara"
    assert isinstance(call_args[1], Desactivar2FARequestDTO)
    assert call_args[1].codigo == "123456"


def test_desactivar_2fa_con_sub_fallback():
    client, mocks = _cliente(claims={"sub": "sub-clara-fallback"})
    mocks["desactivar_2fa"].ejecutar.return_value = Operacion2FAResponseDTO(
        exito=True,
        mensaje="2fa_desactivado",
    )

    response = client.post(
        "/api/v1/auth/2fa/desactivar",
        json={"contrasena": "ClaveSegura123!", "codigo": "123456"},
    )
    assert response.status_code == 200
    mocks["desactivar_2fa"].ejecutar.assert_called_once()
    call_args, _ = mocks["desactivar_2fa"].ejecutar.call_args
    assert call_args[0] == "sub-clara-fallback"


def test_desactivar_2fa_credenciales_invalidas():
    client, mocks = _cliente()
    mocks["desactivar_2fa"].ejecutar.side_effect = CredencialesInvalidasError("credenciales_invalidas")

    response = client.post(
        "/api/v1/auth/2fa/desactivar",
        json={"contrasena": "ClaveErronea!", "codigo": "123456"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "credenciales_invalidas"


# ==============================================================================
# 10. RECUPERAR CONTRASEÑA
# ==============================================================================


def test_solicitar_recuperacion_con_x_forwarded_for():
    client, mocks = _cliente()
    mocks["solicitar_recuperacion"].ejecutar.return_value = Operacion2FAResponseDTO(
        exito=True,
        mensaje="correo_enviado",
    )

    response = client.post(
        "/api/v1/auth/recuperar-contrasena",
        json={"usuario": "admin@planta.local"},
        headers={"X-Forwarded-For": "203.0.113.88, 10.0.0.1"},
    )
    assert response.status_code == 200
    assert response.json() == {"exito": True, "mensaje": "correo_enviado"}
    mocks["solicitar_recuperacion"].ejecutar.assert_called_once()
    call_args, call_kwargs = mocks["solicitar_recuperacion"].ejecutar.call_args
    assert isinstance(call_args[0], SolicitarRecuperacionDTO)
    assert call_args[0].usuario == "admin@planta.local"
    assert call_kwargs["clave_ip"] == "203.0.113.88"


def test_solicitar_recuperacion_sin_x_forwarded_for():
    client, mocks = _cliente()
    mocks["solicitar_recuperacion"].ejecutar.return_value = Operacion2FAResponseDTO(
        exito=True,
        mensaje="correo_enviado",
    )

    response = client.post(
        "/api/v1/auth/recuperar-contrasena",
        json={"usuario": "admin@planta.local"},
    )
    assert response.status_code == 200
    mocks["solicitar_recuperacion"].ejecutar.assert_called_once()
    _, call_kwargs = mocks["solicitar_recuperacion"].ejecutar.call_args
    assert call_kwargs["clave_ip"] == "testclient"


def test_solicitar_recuperacion_request_none_directo():
    mock_uc = MagicMock()
    mock_uc.ejecutar.return_value = Operacion2FAResponseDTO(exito=True, mensaje="ok")
    dto = SolicitarRecuperacionDTO(usuario="u1")
    res = solicitar_recuperacion_handler(dto, mock_uc, request=None)
    assert res.exito is True
    mock_uc.ejecutar.assert_called_once_with(dto, clave_ip="desconocida")


def test_solicitar_recuperacion_demasiados_intentos():
    client, mocks = _cliente()
    mocks["solicitar_recuperacion"].ejecutar.side_effect = DemasiadosIntentosError(
        "demasiados_intentos",
        retry_after_seg=300,
    )

    response = client.post(
        "/api/v1/auth/recuperar-contrasena",
        json={"usuario": "admin@planta.local"},
    )
    assert response.status_code == 429
    assert response.json()["detail"] == "demasiados_intentos"
    assert response.headers.get("Retry-After") == "300"


# ==============================================================================
# 11. RESTABLECER CONTRASEÑA
# ==============================================================================


def test_restablecer_contrasena_exitoso():
    client, mocks = _cliente()
    mocks["restablecer_contrasena"].ejecutar.return_value = Operacion2FAResponseDTO(
        exito=True,
        mensaje="contrasena_restablecida",
    )

    response = client.post(
        "/api/v1/auth/restablecer-contrasena",
        json={"token": "token-recuperacion-valido", "nueva_contrasena": "NuevaClave123!"},
    )
    assert response.status_code == 200
    assert response.json() == {"exito": True, "mensaje": "contrasena_restablecida"}
    mocks["restablecer_contrasena"].ejecutar.assert_called_once()
    call_args, _ = mocks["restablecer_contrasena"].ejecutar.call_args
    assert isinstance(call_args[0], RestablecerContrasenaDTO)
    assert call_args[0].token == "token-recuperacion-valido"
    assert call_args[0].nueva_contrasena == "NuevaClave123!"


def test_restablecer_contrasena_token_invalido():
    client, mocks = _cliente()
    mocks["restablecer_contrasena"].ejecutar.side_effect = TokenRecuperacionInvalidoError("token_recuperacion_invalido")

    response = client.post(
        "/api/v1/auth/restablecer-contrasena",
        json={"token": "token-invalido", "nueva_contrasena": "NuevaClave123!"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "token_recuperacion_invalido"


def test_restablecer_contrasena_debil():
    client, mocks = _cliente()
    mocks["restablecer_contrasena"].ejecutar.side_effect = ContrasenaDebilError("contrasena_debil")

    response = client.post(
        "/api/v1/auth/restablecer-contrasena",
        json={"token": "token-valido", "nueva_contrasena": "123"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "contrasena_debil"


# ==============================================================================
# 12. REVOCAR DISPOSITIVOS CONFIABLES
# ==============================================================================


def test_revocar_dispositivos_exitoso():
    client, mocks = _cliente(claims={"sub": "usuario-uuid-123"})
    mocks["revocar_dispositivos"].ejecutar.return_value = 3

    response = client.post("/api/v1/auth/dispositivos/revocar-todos")
    assert response.status_code == 200
    data = response.json()
    assert data["mensaje"] == "Dispositivos confiables revocados exitosamente"
    assert data["cantidad_revocados"] == 3

    cookie_header = response.headers.get("set-cookie", "")
    assert f"{DEVICE_TRUST_COOKIE}=" in cookie_header
    assert "Path=/api/v1/auth" in cookie_header
    assert "max-age=0" in cookie_header.lower() or "expires=" in cookie_header.lower()
    mocks["revocar_dispositivos"].ejecutar.assert_called_once_with("usuario-uuid-123")


def test_revocar_dispositivos_error():
    client, mocks = _cliente()
    mocks["revocar_dispositivos"].ejecutar.side_effect = RuntimeError("error_db_dispositivos")

    response = client.post("/api/v1/auth/dispositivos/revocar-todos")
    assert response.status_code == 500
    assert response.json()["detail"] == "Ocurrió un error interno en el servidor"

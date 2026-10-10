"""tests/unit/test_oauth_use_cases.py — Tests unitarios de casos de uso OAuth 2.0 PKCE."""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from src.application.dtos.oauth_dtos import (
    OAuthAuthorizeRequestDTO,
    OAuthRevokeRequestDTO,
    OAuthTokenRequestDTO,
)
from src.application.use_cases.oauth.autorizar_consentimiento import AutorizarConsentimientoUseCase
from src.application.use_cases.oauth.canjear_token_oauth import CanjearTokenOAuthUseCase
from src.application.use_cases.oauth.gestionar_integraciones_usuario import (
    GestionarIntegracionesUsuarioUseCase,
)
from src.application.use_cases.oauth.revocar_token_oauth import RevocarTokenOAuthUseCase
from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.ports import GeneradorTokenPort, RepositorioUsuariosPort
from src.domain.oauth.entities import OAuthClient, OAuthCode, OAuthRefreshToken
from src.domain.oauth.exceptions import InvalidClientError, InvalidGrantError, InvalidRequestError
from src.domain.oauth.ports import OAuthRepositoryPort
from src.domain.oauth.services import calcular_code_challenge, hash_token


class InMemoryOAuthRepository(OAuthRepositoryPort):
    def __init__(self) -> None:
        self.clientes: dict[str, OAuthClient] = {
            "claude-ai": OAuthClient(
                client_id="claude-ai",
                client_name="Claude (Anthropic)",
                redirect_uris=("https://claude.ai/api/mcp/oauth_callback", "https://claude.com/oauth"),
                created_at=datetime.now(timezone.utc),
            )
        }
        self.codigos: dict[str, OAuthCode] = {}
        self.refresh_tokens: dict[str, OAuthRefreshToken] = {}

    def obtener_cliente(self, client_id: str) -> OAuthClient | None:
        return self.clientes.get(client_id)

    def guardar_codigo(self, codigo: OAuthCode) -> None:
        self.codigos[codigo.code_hash] = codigo

    def obtener_codigo(self, code_hash: str) -> OAuthCode | None:
        return self.codigos.get(code_hash)

    def consumir_codigo(self, code_hash: str) -> bool:
        c = self.codigos.get(code_hash)
        if c is None or c.used:
            return False
        # Simular actualización atómica
        self.codigos[code_hash] = OAuthCode(
            code_hash=c.code_hash,
            client_id=c.client_id,
            user_id=c.user_id,
            organization_id=c.organization_id,
            redirect_uri=c.redirect_uri,
            code_challenge=c.code_challenge,
            code_challenge_method=c.code_challenge_method,
            scope=c.scope,
            expires_at=c.expires_at,
            used=True,
            created_at=c.created_at,
        )
        return True

    def guardar_refresh_token(self, refresh_token: OAuthRefreshToken) -> None:
        self.refresh_tokens[refresh_token.token_hash] = refresh_token

    def obtener_refresh_token(self, token_hash: str) -> OAuthRefreshToken | None:
        return self.refresh_tokens.get(token_hash)

    def revocar_refresh_token(self, token_hash: str, ahora: datetime) -> bool:
        t = self.refresh_tokens.get(token_hash)
        if t is None or t.revoked_at is not None:
            return False
        self.refresh_tokens[token_hash] = OAuthRefreshToken(
            token_hash=t.token_hash,
            client_id=t.client_id,
            user_id=t.user_id,
            organization_id=t.organization_id,
            scope=t.scope,
            expires_at=t.expires_at,
            revoked_at=ahora,
            created_at=t.created_at,
        )
        return True

    def revocar_tokens_usuario_cliente(self, user_id: str, client_id: str, ahora: datetime) -> int:
        count = 0
        for h, t in list(self.refresh_tokens.items()):
            if t.user_id == user_id and t.client_id == client_id and t.revoked_at is None:
                self.revocar_refresh_token(h, ahora)
                count += 1
        return count

    def listar_integraciones_usuario(self, user_id: str) -> list[dict[str, Any]]:
        activas: dict[str, dict[str, Any]] = {}
        for t in self.refresh_tokens.values():
            if t.user_id == user_id and t.revoked_at is None:
                c = self.obtener_cliente(t.client_id)
                activas[t.client_id] = {
                    "client_id": t.client_id,
                    "client_name": c.client_name if c else t.client_id,
                    "scope": t.scope,
                    "created_at": t.created_at,
                }
        return list(activas.values())


class FakeTokenService(GeneradorTokenPort):
    def generar(
        self,
        usuario_id: str,
        usuario: str,
        expira_en: datetime,
        rol: str = "operador",
        organizacion_id: str | None = None,
        scope: str | None = None,
        client_id: str | None = None,
    ) -> str:
        return f"fake-jwt-{usuario_id}-{rol}-{scope}-{client_id}"

    def verificar(self, token: str) -> dict[str, Any] | None:
        return {"sub": "u1", "rol": "operador"}

    def generar_mfa(self, usuario_id: str, usuario: str, expira_en: datetime) -> str:
        return "mfa"

    def verificar_mfa(self, token: str) -> dict[str, Any] | None:
        return {}


class FakeUsuariosRepo(RepositorioUsuariosPort):
    def __init__(self) -> None:
        self.u = UsuarioAuth(
            id="u123",
            usuario="ingeniero@datamaq.com",
            hash_contrasena="hash",
            esta_activo=True,
            rol="ingeniero",
            organizacion_id="org-durax",
            totp_secret=None,
            totp_enabled=False,
            totp_backup_codes=None,
            sesiones_revocadas_antes_de=None,
            creado_en=datetime.now(timezone.utc),
            actualizado_en=datetime.now(timezone.utc),
        )

    def obtener_por_usuario(self, usuario: str) -> UsuarioAuth | None:
        return self.u if usuario == self.u.usuario else None

    def obtener_por_id(self, usuario_id: str) -> UsuarioAuth | None:
        return self.u if usuario_id == self.u.id else None

    def guardar(self, usuario: UsuarioAuth) -> UsuarioAuth:
        return usuario


@pytest.fixture
def repo():
    return InMemoryOAuthRepository()


@pytest.fixture
def token_service():
    return FakeTokenService()


@pytest.fixture
def usuario_repo():
    return FakeUsuariosRepo()


def test_autorizar_consentimiento_flujo_exitoso(repo):
    uc = AutorizarConsentimientoUseCase(repo)
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = calcular_code_challenge(verifier)

    dto = OAuthAuthorizeRequestDTO(
        client_id="claude-ai",
        redirect_uri="https://claude.ai/api/mcp/oauth_callback",
        code_challenge=challenge,
        code_challenge_method="S256",
        state="xyz123",
        scope="read:telemetria read:analitica",
    )

    res = uc.ejecutar(dto, usuario_id="u123", organizacion_id="org-durax")

    assert res.code is not None
    assert res.state == "xyz123"
    assert "https://claude.ai/api/mcp/oauth_callback?code=" in res.redirect_uri
    assert "&state=xyz123" in res.redirect_uri

    stored = repo.obtener_codigo(hash_token(res.code))
    assert stored is not None
    assert stored.used is False
    assert stored.client_id == "claude-ai"
    assert stored.code_challenge == challenge


def test_autorizar_consentimiento_cliente_desconocido(repo):
    uc = AutorizarConsentimientoUseCase(repo)
    dto = OAuthAuthorizeRequestDTO(
        client_id="cliente-desconocido",
        redirect_uri="https://ejemplo.com/callback",
        code_challenge="dummy_challenge_43_chars_long_minimum_required_ok",
        code_challenge_method="S256",
    )
    with pytest.raises(InvalidClientError):
        uc.ejecutar(dto, usuario_id="u123")


def test_autorizar_consentimiento_redirect_uri_no_autorizada(repo):
    uc = AutorizarConsentimientoUseCase(repo)
    dto = OAuthAuthorizeRequestDTO(
        client_id="claude-ai",
        redirect_uri="https://sitio-malicioso.com/callback",
        code_challenge="dummy_challenge_43_chars_long_minimum_required_ok",
        code_challenge_method="S256",
    )
    with pytest.raises(InvalidRequestError):
        uc.ejecutar(dto, usuario_id="u123")


def test_canjear_codigo_exitoso_y_refrescar(repo, token_service, usuario_repo):
    auth_uc = AutorizarConsentimientoUseCase(repo)
    token_uc = CanjearTokenOAuthUseCase(repo, token_service, usuario_repo)

    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = calcular_code_challenge(verifier)

    auth_dto = OAuthAuthorizeRequestDTO(
        client_id="claude-ai",
        redirect_uri="https://claude.ai/api/mcp/oauth_callback",
        code_challenge=challenge,
        code_challenge_method="S256",
        scope="read:telemetria",
    )
    auth_res = auth_uc.ejecutar(auth_dto, usuario_id="u123", organizacion_id="org-durax")

    # Canje de code
    token_dto = OAuthTokenRequestDTO(
        grant_type="authorization_code",
        client_id="claude-ai",
        code=auth_res.code,
        code_verifier=verifier,
        redirect_uri="https://claude.ai/api/mcp/oauth_callback",
    )
    token_res = token_uc.ejecutar(token_dto)

    assert token_res.access_token == "fake-jwt-u123-ingeniero-read:telemetria-claude-ai"
    assert token_res.token_type == "bearer"
    assert token_res.expires_in == 86400
    assert token_res.refresh_token is not None

    # Rotación vía refresh_token
    refresh_dto = OAuthTokenRequestDTO(
        grant_type="refresh_token",
        client_id="claude-ai",
        refresh_token=token_res.refresh_token,
    )
    refresh_res = token_uc.ejecutar(refresh_dto)

    assert refresh_res.access_token is not None
    assert refresh_res.refresh_token != token_res.refresh_token

    # El refresh_token anterior debe quedar revocado
    with pytest.raises(InvalidGrantError):
        token_uc.ejecutar(refresh_dto)


def test_canjear_codigo_verifier_invalido(repo, token_service, usuario_repo):
    auth_uc = AutorizarConsentimientoUseCase(repo)
    token_uc = CanjearTokenOAuthUseCase(repo, token_service, usuario_repo)

    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = calcular_code_challenge(verifier)

    auth_res = auth_uc.ejecutar(
        OAuthAuthorizeRequestDTO(
            client_id="claude-ai",
            redirect_uri="https://claude.ai/api/mcp/oauth_callback",
            code_challenge=challenge,
            code_challenge_method="S256",
        ),
        usuario_id="u123",
    )

    token_dto = OAuthTokenRequestDTO(
        grant_type="authorization_code",
        client_id="claude-ai",
        code=auth_res.code,
        code_verifier="verifier_incorrecto_pero_con_longitud_valida_para_rfc7636",
        redirect_uri="https://claude.ai/api/mcp/oauth_callback",
    )
    with pytest.raises(InvalidGrantError):
        token_uc.ejecutar(token_dto)


def test_prevencion_reutilizacion_de_codigo(repo, token_service, usuario_repo):
    auth_uc = AutorizarConsentimientoUseCase(repo)
    token_uc = CanjearTokenOAuthUseCase(repo, token_service, usuario_repo)

    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = calcular_code_challenge(verifier)

    auth_res = auth_uc.ejecutar(
        OAuthAuthorizeRequestDTO(
            client_id="claude-ai",
            redirect_uri="https://claude.ai/api/mcp/oauth_callback",
            code_challenge=challenge,
            code_challenge_method="S256",
        ),
        usuario_id="u123",
    )

    token_dto = OAuthTokenRequestDTO(
        grant_type="authorization_code",
        client_id="claude-ai",
        code=auth_res.code,
        code_verifier=verifier,
        redirect_uri="https://claude.ai/api/mcp/oauth_callback",
    )
    token_uc.ejecutar(token_dto)

    # Segundo intento con el mismo código debe ser rechazado
    with pytest.raises(InvalidGrantError) as exc_info:
        token_uc.ejecutar(token_dto)
    assert "ya fue utilizado" in str(exc_info.value)


def test_codigo_expirado_rechazado(repo, token_service, usuario_repo):
    token_uc = CanjearTokenOAuthUseCase(repo, token_service, usuario_repo)

    code_val = "expired_code_123"
    code_hash = hash_token(code_val)
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"

    # Insertar código expirado hace 10 minutos
    hace_diez_minutos = datetime.now(timezone.utc) - timedelta(minutes=10)
    repo.guardar_codigo(
        OAuthCode(
            code_hash=code_hash,
            client_id="claude-ai",
            user_id="u123",
            organization_id="org-durax",
            redirect_uri="https://claude.ai/api/mcp/oauth_callback",
            code_challenge=calcular_code_challenge(verifier),
            code_challenge_method="S256",
            scope="read:telemetria",
            expires_at=hace_diez_minutos,
            used=False,
            created_at=hace_diez_minutos - timedelta(minutes=5),
        )
    )

    token_dto = OAuthTokenRequestDTO(
        grant_type="authorization_code",
        client_id="claude-ai",
        code=code_val,
        code_verifier=verifier,
        redirect_uri="https://claude.ai/api/mcp/oauth_callback",
    )
    with pytest.raises(InvalidGrantError) as exc_info:
        token_uc.ejecutar(token_dto)
    assert "ha expirado" in str(exc_info.value)


def test_revocar_token_rfc7009_y_gestion_integraciones(repo, token_service, usuario_repo):
    auth_uc = AutorizarConsentimientoUseCase(repo)
    token_uc = CanjearTokenOAuthUseCase(repo, token_service, usuario_repo)
    revoke_uc = RevocarTokenOAuthUseCase(repo)
    integraciones_uc = GestionarIntegracionesUsuarioUseCase(repo)

    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    auth_res = auth_uc.ejecutar(
        OAuthAuthorizeRequestDTO(
            client_id="claude-ai",
            redirect_uri="https://claude.ai/api/mcp/oauth_callback",
            code_challenge=calcular_code_challenge(verifier),
            code_challenge_method="S256",
        ),
        usuario_id="u123",
    )
    token_res = token_uc.ejecutar(
        OAuthTokenRequestDTO(
            grant_type="authorization_code",
            client_id="claude-ai",
            code=auth_res.code,
            code_verifier=verifier,
            redirect_uri="https://claude.ai/api/mcp/oauth_callback",
        )
    )

    # Listar integraciones
    lista = integraciones_uc.listar("u123")
    assert len(lista) == 1
    assert lista[0]["client_id"] == "claude-ai"
    assert lista[0]["client_name"] == "Claude (Anthropic)"

    # Revocar token específico
    revoke_uc.ejecutar(OAuthRevokeRequestDTO(token=token_res.refresh_token))

    # Ya no debe estar activo
    assert len(integraciones_uc.listar("u123")) == 0

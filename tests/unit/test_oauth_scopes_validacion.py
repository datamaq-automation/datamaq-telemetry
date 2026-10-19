"""tests/unit/test_oauth_scopes_validacion.py — Scopes OAuth: los desconocidos se descartan (Issue #54, H-A).

RFC 6749 §3.3 permite otorgar un scope reducido. El servidor no aplica scopes todavía (H-B), así que rechazar
desconocidos no protege nada y rompería conectores. Se otorga la intersección con los conocidos; si queda vacía,
los defaults. Cada descarte se registra en WARNING (client_id y scopes, sin datos personales).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from structlog.testing import capture_logs

from src.application.dtos.oauth_dtos import OAuthAuthorizeRequestDTO
from src.application.use_cases.oauth.autorizar_consentimiento import AutorizarConsentimientoUseCase
from src.domain.oauth.entities import OAuthClient
from src.domain.oauth.services import resolver_scopes

CHALLENGE = "a" * 43
DEFAULTS = "read:telemetria read:analitica read:alertas"


def _repo_con_cliente() -> MagicMock:
    repo = MagicMock()
    repo.obtener_cliente.return_value = OAuthClient(
        client_id="claude-ai",
        client_name="Claude (Anthropic)",
        redirect_uris=("https://claude.ai/api/mcp/oauth/callback",),
        created_at=datetime.now(timezone.utc),
    )
    return repo


def _dto(scope: str) -> OAuthAuthorizeRequestDTO:
    return OAuthAuthorizeRequestDTO(
        client_id="claude-ai",
        redirect_uri="https://claude.ai/api/mcp/oauth/callback",
        code_challenge=CHALLENGE,
        scope=scope,
    )


def test_scopes_conocidos_se_otorgan_tal_cual():
    assert resolver_scopes("read:telemetria read:alertas") == ("read:telemetria read:alertas", ())


def test_normaliza_espacios_y_duplicados():
    assert resolver_scopes("  read:alertas   read:alertas read:telemetria ") == (
        "read:alertas read:telemetria",
        (),
    )


def test_desconocido_se_descarta_y_se_otorga_la_interseccion():
    assert resolver_scopes("read:alertas read:todo") == ("read:alertas", ("read:todo",))


def test_solo_desconocidos_usa_los_defaults():
    assert resolver_scopes("read:todo admin") == (DEFAULTS, ("read:todo", "admin"))


def test_sin_scope_usa_los_defaults():
    assert resolver_scopes("") == (DEFAULTS, ())


def test_caso_de_uso_guarda_la_interseccion_y_registra_el_descarte():
    repo = _repo_con_cliente()

    with capture_logs() as logs:
        AutorizarConsentimientoUseCase(repo).ejecutar(
            _dto("read:alertas read:todo"), usuario_id="usr-1", organizacion_id="org-1"
        )

    assert repo.guardar_codigo.call_args.args[0].scope == "read:alertas"
    avisos = [e for e in logs if e["event"] == "oauth_scopes_desconocidos_descartados"]
    assert len(avisos) == 1
    assert avisos[0]["log_level"] == "warning"
    assert avisos[0]["client_id"] == "claude-ai"
    assert avisos[0]["descartados"] == ["read:todo"]
    assert "usr-1" not in str(avisos[0])


def test_caso_de_uso_con_solo_desconocidos_emite_con_defaults():
    repo = _repo_con_cliente()

    AutorizarConsentimientoUseCase(repo).ejecutar(_dto("read:todo"), usuario_id="usr-1", organizacion_id="org-1")

    assert repo.guardar_codigo.call_args.args[0].scope == DEFAULTS


def test_caso_de_uso_con_scopes_conocidos_no_registra_aviso():
    repo = _repo_con_cliente()

    with capture_logs() as logs:
        AutorizarConsentimientoUseCase(repo).ejecutar(
            _dto("read:telemetria"), usuario_id="usr-1", organizacion_id="org-1"
        )

    assert not [e for e in logs if e["event"] == "oauth_scopes_desconocidos_descartados"]

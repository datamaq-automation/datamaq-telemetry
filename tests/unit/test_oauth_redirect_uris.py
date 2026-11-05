"""tests/unit/test_oauth_redirect_uris.py — Issue datamaq#131: redirect_uris de OAuth, dominio y casos de uso.

Coincidencia exacta (sin prefijos ni comodines), excepción de loopback (RFC 8252 §7.3), lista cerrada de Claude,
nombres que no se hacen pasar por Claude y `state` codificado.
"""

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from src.application.dtos.oauth_dtos import OAuthAuthorizeRequestDTO
from src.application.use_cases.oauth.autorizar_consentimiento import AutorizarConsentimientoUseCase
from src.application.use_cases.oauth.registrar_cliente_oauth import RegistrarClienteOAuthUseCase
from src.domain.oauth.entities import OAuthClient
from src.domain.oauth.exceptions import InvalidClientError, InvalidRequestError
from src.domain.oauth.services import (
    CLIENT_ID_CLAUDE,
    URIS_REDIRECT_CLAUDE_POR_DEFECTO,
    construir_url_retorno,
    es_cliente_oficial_de_claude,
    nombre_visible_de_cliente,
    redirect_uri_autorizada,
)

OFICIAL = URIS_REDIRECT_CLAUDE_POR_DEFECTO[1]  # https://claude.ai/api/mcp/oauth_callback
AJENA = "https://evil.example/cb?src=claude.ai"
DESAFIO = "x" * 43


# --- Dominio ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("uri", URIS_REDIRECT_CLAUDE_POR_DEFECTO)
def test_las_cuatro_uris_oficiales_coinciden_con_ellas_mismas(uri):
    assert redirect_uri_autorizada(uri, URIS_REDIRECT_CLAUDE_POR_DEFECTO)


@pytest.mark.parametrize(
    "solicitada",
    [
        OFICIAL + ".evil.test/x",  # extiende por prefijo
        OFICIAL + "/extra",  # prefijo con segmento de ruta
        OFICIAL + "?x=1",  # agrega consulta
        "https://claude.ai.evil.test/api/mcp/oauth_callback",  # subdominio engañoso
        "http://claude.ai/api/mcp/oauth_callback",  # otro esquema
        "https://claude.ai:8443/api/mcp/oauth_callback",  # otro puerto
        AJENA,
    ],
)
def test_una_uri_que_no_es_exactamente_oficial_no_coincide(solicitada):
    assert not redirect_uri_autorizada(solicitada, URIS_REDIRECT_CLAUDE_POR_DEFECTO)


def test_un_asterisco_registrado_no_es_comodin():
    assert not redirect_uri_autorizada("https://a.test/cb/otra", ["https://a.test/cb*"])
    assert not redirect_uri_autorizada("https://a.test/cbX", ["https://a.test/cb*"])


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_la_uri_de_loopback_admite_cualquier_puerto(host):
    registrada = f"http://{host}:8000/callback"

    assert redirect_uri_autorizada(f"http://{host}:51234/callback", [registrada])


@pytest.mark.parametrize(
    "solicitada",
    [
        "http://127.0.0.1:51234/otra",  # otra ruta
        "https://127.0.0.1:51234/callback",  # otro esquema
        "http://localhost:51234/callback",  # otro host
        "http://127.0.0.1:51234/callback?x=1",  # otra consulta
    ],
)
def test_el_loopback_solo_flexibiliza_el_puerto(solicitada):
    assert not redirect_uri_autorizada(solicitada, ["http://127.0.0.1:8000/callback"])


def test_el_puerto_libre_no_aplica_a_hosts_que_no_son_loopback():
    assert not redirect_uri_autorizada("http://evil.test:9999/callback", ["http://evil.test:8000/callback"])


def test_es_cliente_oficial_exige_que_todas_las_uris_esten_en_la_lista():
    assert es_cliente_oficial_de_claude([OFICIAL], URIS_REDIRECT_CLAUDE_POR_DEFECTO)
    assert es_cliente_oficial_de_claude(list(URIS_REDIRECT_CLAUDE_POR_DEFECTO), URIS_REDIRECT_CLAUDE_POR_DEFECTO)
    assert not es_cliente_oficial_de_claude([OFICIAL, AJENA], URIS_REDIRECT_CLAUDE_POR_DEFECTO)
    assert not es_cliente_oficial_de_claude([AJENA], URIS_REDIRECT_CLAUDE_POR_DEFECTO)
    assert not es_cliente_oficial_de_claude([], URIS_REDIRECT_CLAUDE_POR_DEFECTO)


def test_el_nombre_de_un_cliente_externo_no_se_hace_pasar_por_claude():
    assert nombre_visible_de_cliente("Claude (Anthropic)", oficial=False) == "Externo: Claude (Anthropic)"
    assert nombre_visible_de_cliente("ANTHROPIC support", oficial=False) == "Externo: ANTHROPIC support"
    assert nombre_visible_de_cliente("Mi integración", oficial=False) == "Mi integración"
    assert nombre_visible_de_cliente(None, oficial=False) == "Cliente Dinámico"
    assert len(nombre_visible_de_cliente("claude " * 40, oficial=False)) <= 128


def test_el_nombre_del_cliente_oficial_se_conserva():
    assert nombre_visible_de_cliente("Claude", oficial=True) == "Claude"
    assert nombre_visible_de_cliente(None, oficial=True) == "Claude (Anthropic)"


def test_el_state_se_codifica_y_no_inyecta_parametros():
    url = construir_url_retorno("https://a.test/cb", {"code": "abc", "state": "x&code=robado#frag"})

    consulta = parse_qs(urlparse(url).query)
    assert consulta["code"] == ["abc"]
    assert consulta["state"] == ["x&code=robado#frag"]


def test_construir_url_retorno_respeta_la_consulta_existente():
    assert construir_url_retorno("https://a.test/cb?x=1", {"code": "abc"}) == "https://a.test/cb?x=1&code=abc"


# --- Casos de uso ----------------------------------------------------------------------------------------------


class _RepoOAuth:
    """Doble en memoria con la misma semántica de unión que el repositorio real, para probar que el caso de uso
    no la invoca sobre un cliente existente."""

    def __init__(self) -> None:
        self.clientes: dict[str, OAuthClient] = {}
        self.registros: list[str] = []
        self.codigos: list = []

    def obtener_cliente(self, client_id):
        return self.clientes.get(client_id)

    def registrar_o_actualizar_cliente(self, client_id, client_name, redirect_uris):
        self.registros.append(client_id)
        previo = self.clientes.get(client_id)
        uris = sorted(set(redirect_uris) | set(previo.redirect_uris if previo else ()))
        cliente = OAuthClient(client_id, client_name, tuple(uris), datetime.now(timezone.utc))
        self.clientes[client_id] = cliente
        return cliente

    def guardar_codigo(self, codigo):
        self.codigos.append(codigo)


def _dto(redirect_uri: str, client_id: str = CLIENT_ID_CLAUDE, state: str | None = None) -> OAuthAuthorizeRequestDTO:
    return OAuthAuthorizeRequestDTO(
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=DESAFIO,
        code_challenge_method="S256",
        state=state,
    )


def test_registro_oficial_devuelve_el_cliente_fijo_y_no_lo_modifica_si_ya_existe():
    repo = _RepoOAuth()
    caso = RegistrarClienteOAuthUseCase(repo)

    primero = caso.ejecutar("Claude", [OFICIAL])
    segundo = caso.ejecutar("Otro nombre", [OFICIAL])

    assert primero.client_id == segundo.client_id == CLIENT_ID_CLAUDE
    assert repo.registros == [CLIENT_ID_CLAUDE]  # el segundo registro no llegó a escribir
    assert segundo.client_name == "Claude"
    assert segundo.redirect_uris == URIS_REDIRECT_CLAUDE_POR_DEFECTO


def test_registro_con_una_uri_ajena_recibe_su_propio_cliente_y_no_toca_a_claude():
    repo = _RepoOAuth()
    caso = RegistrarClienteOAuthUseCase(repo)
    caso.ejecutar("Claude", [OFICIAL])

    ajeno = caso.ejecutar("Claude (Anthropic)", [AJENA])

    assert ajeno.client_id.startswith("dyn-")
    assert ajeno.client_name == "Externo: Claude (Anthropic)"
    assert ajeno.redirect_uris == (AJENA,)
    assert repo.clientes[CLIENT_ID_CLAUDE].redirect_uris == URIS_REDIRECT_CLAUDE_POR_DEFECTO


def test_registro_mezclando_una_oficial_y_una_ajena_no_obtiene_el_cliente_de_claude():
    repo = _RepoOAuth()

    cliente = RegistrarClienteOAuthUseCase(repo).ejecutar("Claude", [OFICIAL, AJENA])

    assert cliente.client_id.startswith("dyn-")


def test_autorizar_rechaza_la_uri_ajena_para_claude_aunque_la_fila_ya_este_envenenada():
    repo = _RepoOAuth()
    repo.clientes[CLIENT_ID_CLAUDE] = OAuthClient(
        CLIENT_ID_CLAUDE, "Claude", (OFICIAL, AJENA), datetime.now(timezone.utc)
    )

    with pytest.raises(InvalidRequestError):
        AutorizarConsentimientoUseCase(repo).ejecutar(_dto(AJENA), usuario_id="u1")


def test_autorizar_para_otro_cliente_usa_sus_uris_registradas():
    repo = _RepoOAuth()
    repo.clientes["dyn-1"] = OAuthClient("dyn-1", "Mi app", ("https://app.test/cb",), datetime.now(timezone.utc))
    caso = AutorizarConsentimientoUseCase(repo)

    assert caso.ejecutar(_dto("https://app.test/cb", "dyn-1"), usuario_id="u1").code
    with pytest.raises(InvalidRequestError):
        caso.ejecutar(_dto("https://app.test/cb/otra", "dyn-1"), usuario_id="u1")


def test_autorizar_un_cliente_inexistente_responde_invalid_client():
    with pytest.raises(InvalidClientError):
        AutorizarConsentimientoUseCase(_RepoOAuth()).ejecutar(_dto(OFICIAL, "no-existe"), usuario_id="u1")


def test_autorizar_codifica_el_state():
    repo = _RepoOAuth()
    repo.clientes[CLIENT_ID_CLAUDE] = OAuthClient(
        CLIENT_ID_CLAUDE, "Claude", URIS_REDIRECT_CLAUDE_POR_DEFECTO, datetime.now(timezone.utc)
    )

    respuesta = AutorizarConsentimientoUseCase(repo).ejecutar(_dto(OFICIAL, state="x&code=robado"), usuario_id="u1")

    consulta = parse_qs(urlparse(respuesta.redirect_uri).query)
    assert len(consulta["code"]) == 1
    assert consulta["state"] == ["x&code=robado"]


def test_cancelar_solo_redirige_a_una_uri_autorizada():
    repo = _RepoOAuth()
    repo.clientes[CLIENT_ID_CLAUDE] = OAuthClient(
        CLIENT_ID_CLAUDE, "Claude", URIS_REDIRECT_CLAUDE_POR_DEFECTO, datetime.now(timezone.utc)
    )
    caso = AutorizarConsentimientoUseCase(repo)

    url = caso.cancelar(CLIENT_ID_CLAUDE, OFICIAL, state="s&x=1")

    consulta = parse_qs(urlparse(url).query)
    assert consulta["error"] == ["access_denied"]
    assert consulta["state"] == ["s&x=1"]
    with pytest.raises(InvalidRequestError):
        caso.cancelar(CLIENT_ID_CLAUDE, "https://evil.example/phishing", state=None)

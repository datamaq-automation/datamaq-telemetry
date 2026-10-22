"""tests/unit/test_oauth_pkce.py — Pruebas unitarias para validación PKCE S256 según RFC 7636."""

import pytest

from src.domain.oauth.services import (
    calcular_code_challenge,
    generar_token_aleatorio,
    hash_token,
    verificar_code_verifier,
)


def test_pkce_rfc7636_vector_oficial() -> None:
    """Valida el cálculo contra el vector de prueba oficial del RFC 7636 Appendix B."""
    # RFC 7636 Appendix B:
    # code_verifier: dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
    # code_challenge: E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    desafio_esperado = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

    calculado = calcular_code_challenge(verifier)
    assert calculado == desafio_esperado
    assert verificar_code_verifier(verifier, desafio_esperado, method="S256") is True


def test_pkce_verificacion_con_padding_descartado() -> None:
    """Verifica que el desafío tolere challenges con o sin padding '='."""
    verifier = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM_extra_chars_to_reach_43_len"
    challenge = calcular_code_challenge(verifier)

    assert verificar_code_verifier(verifier, challenge, "S256") is True
    assert verificar_code_verifier(verifier, challenge + "==", "S256") is True


def test_pkce_rechazo_verifier_incorrecto() -> None:
    """Verifica que un verifier diferente falle la validación."""
    verifier1 = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    verifier2 = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjX0"
    challenge1 = calcular_code_challenge(verifier1)

    assert verificar_code_verifier(verifier2, challenge1, "S256") is False


def test_pkce_rechazo_metodo_no_s256() -> None:
    """Verifica que solo el método S256 sea aceptado (rechazo de 'plain' u otros)."""
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = calcular_code_challenge(verifier)

    assert verificar_code_verifier(verifier, challenge, "plain") is False
    assert verificar_code_verifier(verifier, challenge, "S512") is False


@pytest.mark.parametrize(
    "verifier_invalido",
    [
        "corto",  # < 43 caracteres
        "a" * 129,  # > 128 caracteres
        "verifier_con_espacios_no_permitidos_por_rfc7636_" + "a" * 20,
        "verifier_con_caracter_especial_$_" + "a" * 30,
    ],
)
def test_pkce_rechazo_longitudes_y_caracteres_invalidos(verifier_invalido: str) -> None:
    """Rechaza verifiers fuera del rango [43, 128] o con caracteres no permitidos."""
    assert verificar_code_verifier(verifier_invalido, "dummy_challenge", "S256") is False


def test_generar_token_aleatorio_y_hash() -> None:
    """Valida la generación de tokens criptográficos aleatorios y su hash determinístico."""
    t1 = generar_token_aleatorio(32)
    t2 = generar_token_aleatorio(32)
    assert len(t1) >= 40
    assert t1 != t2

    h1 = hash_token(t1)
    h1_repetido = hash_token(t1)
    assert len(h1) == 64
    assert h1 == h1_repetido
    assert h1 != hash_token(t2)

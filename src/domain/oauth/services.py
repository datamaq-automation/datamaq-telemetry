"""src/domain/oauth/services.py — Servicios de dominio para validación PKCE y hashing de tokens."""

import base64
import hashlib
import hmac
import re
import secrets

# RFC 7636 §4.1: [A-Z] / [a-z] / [0-9] / "-" / "." / "_" / "~", longitud de 43 a 128
REGEX_CODE_VERIFIER = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")

# Scopes que el servidor OAuth conoce (scopes_supported del discovery y descripciones de consent-info).
SCOPES_CONOCIDOS: frozenset[str] = frozenset({"read:telemetria", "read:analitica", "read:alertas"})


# Lo que se otorga cuando el pedido no trae ningún scope conocido (RFC 6749 §3.3: el servidor puede reducir el scope).
SCOPES_POR_DEFECTO = ("read:telemetria", "read:analitica", "read:alertas")


def resolver_scopes(solicitados: str) -> tuple[str, tuple[str, ...]]:
    """Scope otorgado y los desconocidos descartados.

    Se otorga la intersección con SCOPES_CONOCIDOS, normalizada (sin duplicados). Si no queda ninguno, se
    otorgan los SCOPES_POR_DEFECTO. Los desconocidos se devuelven aparte para registrarlos.
    """
    pedidos = list(dict.fromkeys(solicitados.split()))
    conocidos = [s for s in pedidos if s in SCOPES_CONOCIDOS]
    descartados = tuple(s for s in pedidos if s not in SCOPES_CONOCIDOS)
    if not conocidos:
        conocidos = list(SCOPES_POR_DEFECTO)
    return " ".join(conocidos), descartados


def calcular_code_challenge(code_verifier: str) -> str:
    """Calcula el code_challenge S256 para un code_verifier según RFC 7636 §4.2."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def verificar_code_verifier(code_verifier: str, code_challenge: str, method: str = "S256") -> bool:
    """Valida un code_verifier contra el code_challenge persistido con resistencia a timing attacks."""
    if method != "S256":
        return False

    if not REGEX_CODE_VERIFIER.match(code_verifier):
        return False

    desafio_calculado = calcular_code_challenge(code_verifier)
    # Normalizar eliminando posible padding trailing
    desafio_esperado = code_challenge.rstrip("=")
    return hmac.compare_digest(desafio_calculado, desafio_esperado)


def generar_token_aleatorio(nbytes: int = 32) -> str:
    """Genera un token/código criptográfico seguro en formato urlsafe."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Calcula el hash SHA-256 para persistencia segura de códigos y refresh tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

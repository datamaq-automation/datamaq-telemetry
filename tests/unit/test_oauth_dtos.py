"""tests/unit/test_oauth_dtos.py."""

import pytest
from pydantic import ValidationError

from src.application.dtos.oauth_dtos import (
    OAuthAuthorizeRequestDTO,
    OAuthConsentProcessRequestDTO,
)


def test_oauth_authorize_request_dto_state_limite_4096():
    """Valida que OAuthAuthorizeRequestDTO permita state de hasta 4096 caracteres y rechace > 4096."""
    state_4096 = "s" * 4096
    dto = OAuthAuthorizeRequestDTO(
        client_id="claude-ai",
        redirect_uri="https://claude.ai/callback",
        code_challenge="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
        code_challenge_method="S256",
        state=state_4096,
    )
    assert dto.state == state_4096

    state_4097 = "s" * 4097
    with pytest.raises(ValidationError):
        OAuthAuthorizeRequestDTO(
            client_id="claude-ai",
            redirect_uri="https://claude.ai/callback",
            code_challenge="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
            code_challenge_method="S256",
            state=state_4097,
        )


def test_oauth_consent_process_request_dto_state_limite_4096():
    """Valida que OAuthConsentProcessRequestDTO permita state de hasta 4096 caracteres y rechace > 4096."""
    state_4096 = "s" * 4096
    dto = OAuthConsentProcessRequestDTO(
        client_id="claude-ai",
        redirect_uri="https://claude.ai/callback",
        code_challenge="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
        code_challenge_method="S256",
        state=state_4096,
        aprobado=True,
    )
    assert dto.state == state_4096

    state_4097 = "s" * 4097
    with pytest.raises(ValidationError):
        OAuthConsentProcessRequestDTO(
            client_id="claude-ai",
            redirect_uri="https://claude.ai/callback",
            code_challenge="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
            code_challenge_method="S256",
            state=state_4097,
            aprobado=True,
        )

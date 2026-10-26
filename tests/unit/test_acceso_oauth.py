"""tests/unit/test_acceso_oauth.py — Chequeo compartido de vigencia de access tokens OAuth (Issue #33)."""

from datetime import datetime, timedelta, timezone
from typing import Any

from src.infrastructure.fastapi.acceso_oauth import TOLERANCIA_EMISION, integracion_oauth_vigente

IAT = 1_760_000_000


class _Repo:
    """Doble mínimo del puerto: registra con qué argumentos lo consultan y responde lo que se le configure."""

    def __init__(self, responde: bool = True, lanza: bool = False) -> None:
        self.responde = responde
        self.lanza = lanza
        self.llamadas: list[tuple[str, str, datetime | None]] = []

    def tiene_integracion_activa(
        self, user_id: str, client_id: str, refresh_creado_hasta: datetime | None = None
    ) -> bool:
        self.llamadas.append((user_id, client_id, refresh_creado_hasta))
        if self.lanza:
            raise RuntimeError("base caída")
        return self.responde


def _claims_oauth(**extra: Any) -> dict[str, Any]:
    return {"sub": "u1", "client_id": "claude-ai", "iat": IAT, **extra}


def test_token_de_login_no_consulta_el_repositorio():
    repo = _Repo()
    assert integracion_oauth_vigente({"sub": "u1", "iat": IAT}, repo) is True  # type: ignore[arg-type]
    assert repo.llamadas == []


def test_token_de_login_vale_aunque_no_haya_repositorio():
    assert integracion_oauth_vigente({"sub": "u1", "iat": IAT}, None) is True


def test_consulta_con_el_iat_del_access_mas_la_tolerancia():
    repo = _Repo(responde=True)
    assert integracion_oauth_vigente(_claims_oauth(), repo) is True  # type: ignore[arg-type]
    esperado = datetime.fromtimestamp(IAT, tz=timezone.utc) + TOLERANCIA_EMISION
    assert repo.llamadas == [("u1", "claude-ai", esperado)]


def test_integracion_desconectada_no_vale():
    assert integracion_oauth_vigente(_claims_oauth(), _Repo(responde=False)) is False  # type: ignore[arg-type]


def test_falla_cerrada_si_el_repositorio_lanza():
    assert integracion_oauth_vigente(_claims_oauth(), _Repo(lanza=True)) is False  # type: ignore[arg-type]


def test_falla_cerrada_sin_repositorio():
    assert integracion_oauth_vigente(_claims_oauth(), None) is False


def test_falla_cerrada_sin_sub_o_sin_iat():
    repo = _Repo()
    assert integracion_oauth_vigente({"client_id": "claude-ai", "iat": IAT}, repo) is False  # type: ignore[arg-type]
    assert integracion_oauth_vigente({"sub": "u1", "client_id": "claude-ai"}, repo) is False  # type: ignore[arg-type]
    assert repo.llamadas == []


def test_la_tolerancia_cubre_el_truncado_del_iat_y_el_redondeo_de_mysql():
    """El refresh se crea con el mismo `ahora` que el access: hasta ~1,5 s después del iat entero no debe cortarlo."""
    assert TOLERANCIA_EMISION >= timedelta(seconds=1.6)

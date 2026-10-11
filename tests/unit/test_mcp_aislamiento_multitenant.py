"""tests/unit/test_mcp_aislamiento_multitenant.py — Verificación de aislamiento multi-tenant con dos tokens y superadmin.

Demuestra y valida formalmente el comportamiento ante el Hallazgo H1:
1. Un token con rol 'superadmin' tiene visibilidad global transversal (devuelve las 4 plantas).
2. Un token de la Organización Durax solo puede listar y consultar plantas de Durax.
3. Un token de la Organización San Martín solo puede listar y consultar plantas de San Martín.
4. Cualquier intento de consulta cruzada (IDOR) entre organizaciones es bloqueado con 404 estricto.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from src.application.dtos.organizacion_dto import PlantaResponseDTO
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from tools.mcp.server import (
    datamaq_analizar_capacitores,
    datamaq_listar_plantas,
    set_client,
)

AHORA = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
SECRET_KEY = "clave-secreta-de-prueba-multitenant"

ORG_DURAX = "cf82b4be-0798-4beb-8978-2a27612d5761"
ORG_SAN_MARTIN = "20857cb6-eff2-4bd4-8cb9-36e4c63bcee3"
ORG_UPP = "edebb9a0-85e5-4bde-a370-e64bd9b9608c"
ORG_CASA = "09c09578-a860-4c61-8e97-2a13240adb8f"

PLANTAS_SISTEMA = [
    PlantaResponseDTO(
        id="planta-durax",
        organizacion_id=ORG_DURAX,
        nombre="Planta Principal Durax",
        slug="durax",
        creado_en=AHORA,
        actualizado_en=AHORA,
    ),
    PlantaResponseDTO(
        id="planta-san-martin",
        organizacion_id=ORG_SAN_MARTIN,
        nombre="Planta San Martín",
        slug="san-martin",
        creado_en=AHORA,
        actualizado_en=AHORA,
    ),
    PlantaResponseDTO(
        id="planta-upp",
        organizacion_id=ORG_UPP,
        nombre="Planta Principal UPP",
        slug="upp",
        creado_en=AHORA,
        actualizado_en=AHORA,
    ),
    PlantaResponseDTO(
        id="planta-casa",
        organizacion_id=ORG_CASA,
        nombre="Casa",
        slug="casa",
        creado_en=AHORA,
        actualizado_en=AHORA,
    ),
]


def _crear_token(
    usuario_id: str,
    email: str,
    rol: str,
    organizacion_id: str | None = None,
) -> str:
    service = JwtTokenService(SECRET_KEY)
    exp = datetime.now(timezone.utc) + timedelta(hours=2)
    # Genera token con payload estándar JWT
    token = service.generar(
        usuario_id=usuario_id,
        usuario=email,
        expira_en=exp,
        rol=rol,
        organizacion_id=organizacion_id,
    )
    return token


def _decodificar_token(token: str) -> dict[str, Any] | None:
    service = JwtTokenService(SECRET_KEY)
    return service.verificar(token)


@pytest.fixture(autouse=True)
def limpiar_cliente_mcp():
    yield
    set_client(None)


@pytest.mark.asyncio
async def test_aislamiento_multitenant_listar_plantas():
    """Valida que un superadmin ve todas las plantas pero tokens de organizaciones específicas solo ven la suya."""
    token_superadmin = _crear_token("usr-super", "super@datamaq.com", rol="superadmin")
    token_durax = _crear_token("usr-durax", "operador@durax.com", rol="operador", organizacion_id=ORG_DURAX)
    token_san_martin = _crear_token("usr-sm", "admin@sanmartin.com", rol="admin", organizacion_id=ORG_SAN_MARTIN)

    def mock_backend(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return httpx.Response(401, json={"detail": "credenciales_invalidas"})
        token_str = auth.removeprefix("Bearer ")
        claims = _decodificar_token(token_str)
        if not claims:
            return httpx.Response(401, json={"detail": "credenciales_invalidas"})

        if request.url.path == "/api/v1/plantas":
            rol = claims.get("rol")
            if rol in ("superadmin", "invitado_global"):
                # Superadmin ve todas las plantas
                return httpx.Response(200, json=[p.model_dump(mode="json") for p in PLANTAS_SISTEMA])

            org = claims.get("org")
            # Usuario regular solo ve las plantas de su propia organizacion
            plantas_org = [p.model_dump(mode="json") for p in PLANTAS_SISTEMA if p.organizacion_id == org]
            return httpx.Response(200, json=plantas_org)

        return httpx.Response(404, json={"detail": "not_found"})

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(mock_backend),
        base_url="http://datamaq.local",
    )
    set_client(mock_client)

    # 1. Caso Superadmin: ve 4 plantas (comportamiento observado en H1 del reporte técnico)
    import os

    os.environ["DATAMAQ_AUTH_TOKEN"] = token_superadmin
    plantas_super = await datamaq_listar_plantas()
    assert len(plantas_super) == 4
    orgs_vistas = {p["organizacion_id"] for p in plantas_super}
    assert orgs_vistas == {ORG_DURAX, ORG_SAN_MARTIN, ORG_UPP, ORG_CASA}

    # 2. Caso Organización Durax: SOLO ve Planta Durax
    os.environ["DATAMAQ_AUTH_TOKEN"] = token_durax
    plantas_durax = await datamaq_listar_plantas()
    assert len(plantas_durax) == 1
    assert plantas_durax[0]["id"] == "planta-durax"
    assert plantas_durax[0]["organizacion_id"] == ORG_DURAX

    # 3. Caso Organización San Martín: SOLO ve Planta San Martín
    os.environ["DATAMAQ_AUTH_TOKEN"] = token_san_martin
    plantas_sm = await datamaq_listar_plantas()
    assert len(plantas_sm) == 1
    assert plantas_sm[0]["id"] == "planta-san-martin"
    assert plantas_sm[0]["organizacion_id"] == ORG_SAN_MARTIN


@pytest.mark.asyncio
async def test_aislamiento_multitenant_idor_acceso_cruzado_bloqueado():
    """Valida que un token de Durax no puede consultar analítica o alertas de San Martín (mitigación IDOR)."""
    token_durax = _crear_token("usr-durax", "operador@durax.com", rol="operador", organizacion_id=ORG_DURAX)
    token_san_martin = _crear_token("usr-sm", "admin@sanmartin.com", rol="admin", organizacion_id=ORG_SAN_MARTIN)

    def mock_backend(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization", "")
        token_str = auth.removeprefix("Bearer ")
        claims = _decodificar_token(token_str)
        if not claims:
            return httpx.Response(401, json={"detail": "credenciales_invalidas"})

        planta_id = request.url.params.get("planta_id")
        planta = next((p for p in PLANTAS_SISTEMA if p.id == planta_id), None)
        if not planta:
            return httpx.Response(404, json={"detail": "planta_no_encontrada"})

        # Política de acceso a plantas: si no es superadmin, solo puede acceder si pertenece a su org
        rol = claims.get("rol")
        org = claims.get("org")
        if rol not in ("superadmin", "invitado_global") and planta.organizacion_id != org:
            # 404 estricto para mitigar IDOR y enumeración de recursos
            return httpx.Response(404, json={"detail": "planta_no_encontrada"})

        if request.url.path == "/api/v1/analitica/banco-capacitores/planta":
            return httpx.Response(
                200,
                json={
                    "planta_id": planta.id,
                    "periodo_dias": 30,
                    "potencia_activa_promedio_kw": 100.0,
                    "potencia_reactiva_promedio_kvar": 40.0,
                    "potencia_reactiva_max_kvar": 60.0,
                    "fp_promedio": 0.92,
                    "fp_objetivo": 0.96,
                    "qc_necesaria_kvar": 15.0,
                    "banco_comercial_sugerido_kvar": 17.5,
                    "escalones_sugeridos_kvar": [10.0, 7.5],
                    "sobrecompensacion_sostenida": False,
                    "razon_no_recomendacion": None,
                    "fecha_calculo": "2026-10-10T12:00:00Z",
                },
            )

        return httpx.Response(404, json={"detail": "not_found"})

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(mock_backend),
        base_url="http://datamaq.local",
    )
    set_client(mock_client)

    import os

    os.environ["DATAMAQ_AUTH_TOKEN"] = token_durax

    # 1. Consulta de su propia planta (Durax): exitosa
    analisis_propio = await datamaq_analizar_capacitores(planta_id="planta-durax", periodo_dias=30)
    assert analisis_propio["planta_id"] == "planta-durax"

    # 2. Intento de acceso cruzado desde Durax a San Martín: falla con 404 (IDOR mitigado)
    with pytest.raises(RuntimeError) as exc_info:
        await datamaq_analizar_capacitores(planta_id="planta-san-martin", periodo_dias=30)

    assert "404" in str(exc_info.value)
    assert "no pertenece a la organización del token" in str(exc_info.value)

    # 3. Intento de acceso cruzado inverso desde San Martín a Durax: falla con 404
    os.environ["DATAMAQ_AUTH_TOKEN"] = token_san_martin
    with pytest.raises(RuntimeError) as exc_info_sm:
        await datamaq_analizar_capacitores(planta_id="planta-durax", periodo_dias=30)

    assert "404" in str(exc_info_sm.value)
    assert "no pertenece a la organización del token" in str(exc_info_sm.value)

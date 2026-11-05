"""tests/unit/test_device_ownership.py — Tests de aislamiento de alertas y dispositivos por planta y organización."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_alerta


def _crear_alerta_mock(alerta_id: int = 1, dispositivo_id: str = "dev-1"):
    alerta = MagicMock()
    alerta.id = alerta_id
    alerta.dispositivo_id = dispositivo_id
    return alerta


def _crear_dispositivo_mock(dispositivo_id: str = "dev-1", planta_id: str = "planta-a1"):
    disp = MagicMock()
    disp.id = dispositivo_id
    disp.planta_id = planta_id
    return disp


def test_verificar_propiedad_alerta_rechaza_404_si_planta_no_autorizada(monkeypatch):
    """C4-7 (Issue #137): Alerta de planta no asignada responde 404 sin revelar existencia."""
    db = MagicMock()
    alerta = _crear_alerta_mock(alerta_id=10, dispositivo_id="dev-planta-ajena")
    disp = _crear_dispositivo_mock(dispositivo_id="dev-planta-ajena", planta_id="planta-ajena")

    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership.get_settings",
        lambda: MagicMock(AUTH_REQUIRED=True),
    )
    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership.MySQLTelemetriaRepository",
        lambda db_session: MagicMock(obtener_alerta_por_id=lambda aid: alerta),
    )
    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership._organizacion_de_dispositivo",
        lambda db_session, dev_id: "org-1",
    )
    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership.repo_dispositivos_resuelto",
        lambda db_session: MagicMock(obtener_por_id=lambda did: disp),
    )

    acceso_plantas = MagicMock()
    acceso_plantas.resolver_planta_permitida.side_effect = PlantaNoEncontradaError("Planta no autorizada")

    claims = {"sub": "user-1", "rol": "operador", "org": "org-1"}

    with pytest.raises(HTTPException) as exc_info:
        verificar_propiedad_alerta(
            claims=claims,
            db=db,
            acceso_plantas=acceso_plantas,
            alerta_id=10,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "alerta_no_encontrada"


def test_verificar_propiedad_alerta_permite_si_planta_autorizada(monkeypatch):
    """Alerta de planta permitida pasa la verificación correctamente."""
    db = MagicMock()
    alerta = _crear_alerta_mock(alerta_id=10, dispositivo_id="dev-planta-propia")
    disp = _crear_dispositivo_mock(dispositivo_id="dev-planta-propia", planta_id="planta-propia")

    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership.get_settings",
        lambda: MagicMock(AUTH_REQUIRED=True),
    )
    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership.MySQLTelemetriaRepository",
        lambda db_session: MagicMock(obtener_alerta_por_id=lambda aid: alerta),
    )
    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership._organizacion_de_dispositivo",
        lambda db_session, dev_id: "org-1",
    )
    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership.repo_dispositivos_resuelto",
        lambda db_session: MagicMock(obtener_por_id=lambda did: disp),
    )

    acceso_plantas = MagicMock()
    acceso_plantas.resolver_planta_permitida.return_value = "planta-propia"

    claims = {"sub": "user-1", "rol": "operador", "org": "org-1"}

    # No debe levantar ninguna excepción
    verificar_propiedad_alerta(
        claims=claims,
        db=db,
        acceso_plantas=acceso_plantas,
        alerta_id=10,
    )


def test_verificar_propiedad_alerta_superadmin_pasa_sin_chequeos():
    """Superadmin no valida acceso por planta ni organización."""
    db = MagicMock()
    acceso_plantas = MagicMock()
    claims = {"sub": "admin-1", "rol": "superadmin"}

    verificar_propiedad_alerta(
        claims=claims,
        db=db,
        acceso_plantas=acceso_plantas,
        alerta_id=999,
    )

    acceso_plantas.resolver_planta_permitida.assert_not_called()

"""tests/unit/test_verificar_propiedad_dispositivo.py — Tests de aislamiento por organización en los endpoints REST de telemetría/dispositivos."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.infrastructure.fastapi.device_ownership import (
    verificar_propiedad_dispositivo,
)


class _FakeDispositivo:
    def __init__(self, planta_id: str | None) -> None:
        self.planta_id = planta_id


class _FakePlanta:
    def __init__(self, organizacion_id: str | None) -> None:
        self.organizacion_id = organizacion_id


class _FakeSettings:
    def __init__(self, auth_required: bool = True) -> None:
        self.AUTH_REQUIRED = auth_required


def _mock_mysql_repos(monkeypatch, repo_dispositivos=None, repo_organizaciones=None):
    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership.MySQLDispositivosRepository",
        lambda db: repo_dispositivos or MagicMock(),
    )
    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership.YamlOrganizacionesRepository",
        lambda *args, **kwargs: repo_organizaciones or MagicMock(),
    )


class TestVerificarPropiedadDispositivo:
    def test_superadmin_pasa_sin_consultar_repos(self, monkeypatch):
        repo_dispositivos = MagicMock()
        _mock_mysql_repos(monkeypatch, repo_dispositivos=repo_dispositivos)
        with patch(
            "src.infrastructure.fastapi.device_ownership.get_settings",
            return_value=_FakeSettings(auth_required=True),
        ):
            verificar_propiedad_dispositivo(claims={"rol": "superadmin"}, db=MagicMock(), device_id="cualquier-id")
        repo_dispositivos.obtener_por_id.assert_not_called()

    def test_sin_auth_required_pasa_sin_consultar_repos(self, monkeypatch):
        repo_dispositivos = MagicMock()
        _mock_mysql_repos(monkeypatch, repo_dispositivos=repo_dispositivos)
        with patch(
            "src.infrastructure.fastapi.device_ownership.get_settings",
            return_value=_FakeSettings(auth_required=False),
        ):
            verificar_propiedad_dispositivo(claims={"rol": "admin"}, db=MagicMock(), device_id="cualquier-id")
        repo_dispositivos.obtener_por_id.assert_not_called()

    def test_sin_device_id_ni_dispositivo_id_pasa(self, monkeypatch):
        repo_dispositivos = MagicMock()
        _mock_mysql_repos(monkeypatch, repo_dispositivos=repo_dispositivos)
        with patch(
            "src.infrastructure.fastapi.device_ownership.get_settings",
            return_value=_FakeSettings(auth_required=True),
        ):
            verificar_propiedad_dispositivo(claims={"rol": "operador", "org": "org-a"}, db=MagicMock())
        repo_dispositivos.obtener_por_id.assert_not_called()

    def test_usuario_de_org_a_ve_dispositivo_de_org_a(self, monkeypatch):
        repo_dispositivos = MagicMock()
        repo_dispositivos.obtener_por_id.return_value = _FakeDispositivo(planta_id="planta-1")
        repo_organizaciones = MagicMock()
        repo_organizaciones.obtener_planta_por_id.return_value = _FakePlanta(organizacion_id="org-a")
        _mock_mysql_repos(monkeypatch, repo_dispositivos, repo_organizaciones)

        with patch(
            "src.infrastructure.fastapi.device_ownership.get_settings",
            return_value=_FakeSettings(auth_required=True),
        ):
            verificar_propiedad_dispositivo(
                claims={"rol": "operador", "org": "org-a"}, db=MagicMock(), device_id="dev-1"
            )

    def test_usuario_de_org_a_no_ve_dispositivo_de_org_b(self, monkeypatch):
        repo_dispositivos = MagicMock()
        repo_dispositivos.obtener_por_id.return_value = _FakeDispositivo(planta_id="planta-2")
        repo_organizaciones = MagicMock()
        repo_organizaciones.obtener_planta_por_id.return_value = _FakePlanta(organizacion_id="org-b")
        _mock_mysql_repos(monkeypatch, repo_dispositivos, repo_organizaciones)

        with patch(
            "src.infrastructure.fastapi.device_ownership.get_settings",
            return_value=_FakeSettings(auth_required=True),
        ):
            with pytest.raises(HTTPException) as exc_info:
                verificar_propiedad_dispositivo(
                    claims={"rol": "operador", "org": "org-a"}, db=MagicMock(), device_id="dev-2"
                )
        assert exc_info.value.status_code == 404

    def test_dispositivo_inexistente_devuelve_404(self, monkeypatch):
        repo_dispositivos = MagicMock()
        repo_dispositivos.obtener_por_id.return_value = None
        repo_dispositivos.obtener_por_uid.side_effect = Exception("mac invalida")
        _mock_mysql_repos(monkeypatch, repo_dispositivos=repo_dispositivos)

        with patch(
            "src.infrastructure.fastapi.device_ownership.get_settings",
            return_value=_FakeSettings(auth_required=True),
        ):
            with pytest.raises(HTTPException) as exc_info:
                verificar_propiedad_dispositivo(
                    claims={"rol": "operador", "org": "org-a"}, db=MagicMock(), device_id="no-existe"
                )
        assert exc_info.value.status_code == 404

    def test_dispositivo_sin_planta_devuelve_404_para_no_superadmin(self, monkeypatch):
        repo_dispositivos = MagicMock()
        repo_dispositivos.obtener_por_id.return_value = _FakeDispositivo(planta_id=None)
        repo_organizaciones = MagicMock()
        _mock_mysql_repos(monkeypatch, repo_dispositivos, repo_organizaciones)

        with patch(
            "src.infrastructure.fastapi.device_ownership.get_settings",
            return_value=_FakeSettings(auth_required=True),
        ):
            with pytest.raises(HTTPException) as exc_info:
                verificar_propiedad_dispositivo(
                    claims={"rol": "operador", "org": "org-a"}, db=MagicMock(), device_id="dev-3"
                )
        assert exc_info.value.status_code == 404
        repo_organizaciones.obtener_planta_por_id.assert_not_called()

    def test_dispositivo_id_query_param_tambien_funciona(self, monkeypatch):
        """El endpoint de exportar CSV usa `dispositivo_id` (query) en vez de `device_id` (path)."""
        repo_dispositivos = MagicMock()
        repo_dispositivos.obtener_por_id.return_value = _FakeDispositivo(planta_id="planta-1")
        repo_organizaciones = MagicMock()
        repo_organizaciones.obtener_planta_por_id.return_value = _FakePlanta(organizacion_id="org-a")
        _mock_mysql_repos(monkeypatch, repo_dispositivos, repo_organizaciones)

        with patch(
            "src.infrastructure.fastapi.device_ownership.get_settings",
            return_value=_FakeSettings(auth_required=True),
        ):
            verificar_propiedad_dispositivo(
                claims={"rol": "operador", "org": "org-a"}, db=MagicMock(), dispositivo_id="dev-1"
            )

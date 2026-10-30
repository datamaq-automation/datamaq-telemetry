"""tests/unit/test_verificador_propiedad_dispositivo.py — verificador de propiedad con la sesión ligada."""

from src.infrastructure.fastapi import device_ownership


def test_verificador_delega_en_verificar_propiedad_con_la_sesion_ligada(monkeypatch):
    llamadas: list[dict] = []

    def _falsa(**kwargs) -> None:
        llamadas.append(kwargs)

    monkeypatch.setattr(device_ownership, "verificar_propiedad_dispositivo", _falsa)
    sesion = object()
    verificar = device_ownership.crear_verificador_propiedad(sesion)

    verificar({"rol": "admin"}, "dev-1")

    assert llamadas == [{"claims": {"rol": "admin"}, "db": sesion, "dispositivo_id": "dev-1"}]

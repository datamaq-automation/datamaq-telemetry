"""tests/unit/test_plantas_determinismo.py — Valida determinismo de creado_en/actualizado_en en plantas."""

from datetime import datetime, timezone

from src.infrastructure.yaml.repositories.organizaciones_repository import (
    _FECHA_DECLARATIVA_BASE,
    YamlOrganizacionesRepository,
)


def test_plantas_yaml_tienen_creado_en_determinista():
    repo = YamlOrganizacionesRepository()
    plantas_1 = repo.listar_plantas()
    plantas_2 = repo.listar_plantas()

    assert len(plantas_1) > 0
    assert len(plantas_1) == len(plantas_2)

    for p1, p2 in zip(plantas_1, plantas_2, strict=True):
        assert p1.creado_en == p2.creado_en
        assert p1.actualizado_en == p2.actualizado_en
        assert p1.creado_en == _FECHA_DECLARATIVA_BASE
        assert p1.creado_en.tzinfo == timezone.utc


def test_planta_parsea_creado_en_explicito_si_existe():
    fecha_custom = "2025-05-10T14:30:00Z"
    planta_raw = {
        "id": "planta-custom",
        "nombre": "Planta Custom",
        "creado_en": fecha_custom,
    }
    # Simulamos el helper
    from src.infrastructure.yaml.repositories.organizaciones_repository import _parsear_fecha_opt

    dt = _parsear_fecha_opt(planta_raw.get("creado_en"), _FECHA_DECLARATIVA_BASE)
    assert dt == datetime(2025, 5, 10, 14, 30, 0, tzinfo=timezone.utc)

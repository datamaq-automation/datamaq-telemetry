"""tests/unit/test_energia_agregada_dto.py — El DTO de energía por periodo expone el hueco absorbido (#18)."""

from datetime import date

from src.application.mappers.telemetria_mapper import TelemetriaMapper
from src.domain.telemetria.entities import EnergiaAgregada


def test_dto_expone_periodos_sin_datos_previos():
    dto = TelemetriaMapper.energia_agregada_to_dto(
        EnergiaAgregada(periodo=date(2026, 9, 14), energia_activa_neta_kwh=19_780.5, periodos_sin_datos_previos=1)
    )
    assert dto.periodos_sin_datos_previos == 1


def test_dto_por_defecto_no_marca_hueco():
    dto = TelemetriaMapper.energia_agregada_to_dto(
        EnergiaAgregada(periodo=date(2026, 9, 15), energia_activa_neta_kwh=1.0)
    )
    assert dto.periodos_sin_datos_previos == 0

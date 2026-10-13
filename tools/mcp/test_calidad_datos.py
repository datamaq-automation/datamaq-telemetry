"""tools/mcp/test_calidad_datos.py — Compuerta de calidad de datos del MCP (#31), capa pura.

Fixtures en memoria: sin base real ni HTTP. Los casos siguen la matriz del spec-issue-31.md (sección 6).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from tools.mcp.server import (
    _bloquea_calculo,
    _evaluar_medidor,
    _fases_desde_config,
    _resumen_calidad,
)

PUNTOS_5_MIN_EN_UNA_HORA = 12


def _lecturas(potencias_w: list[float]) -> list[dict[str, Any]]:
    """Una lectura por bucket de 5 min, con P ya promediada por bucket (un valor por bucket)."""
    return [
        {"registrado_en": f"2026-10-06T{(i // 12):02d}:{(i % 12) * 5:02d}:00Z", "potencia_activa_total_W": p}
        for i, p in enumerate(potencias_w)
    ]


def _medidor(**extra: Any) -> dict[str, Any]:
    base = {"id": "dev-1", "ubicacion_tag": "Trafo 2", "tipo_instalacion": "CONSUMO", "fases_con_ti": "R,S,T"}
    base.update(extra)
    return base


def test_fases_desde_config_detecta_fases_faltantes() -> None:
    assert _fases_desde_config("R,S") == (["R", "S"], ["T"])
    assert _fases_desde_config("r, s, t") == (["R", "S", "T"], [])
    assert _fases_desde_config(None) == (["R", "S", "T"], [])


def test_medidor_sano_no_tiene_codigos() -> None:
    """T8: planta sana, P positiva, trifásico y cobertura completa: sin sospecha."""
    ev = _evaluar_medidor(_medidor(), _lecturas([30_000.0] * 12), [], PUNTOS_5_MIN_EN_UNA_HORA)

    assert ev["codigos"] == []
    assert ev["fases_faltantes"] == []


def test_p_negativa_sostenida_en_consumo_activa_s2() -> None:
    """T1: P < -100 W en 60% de los buckets en un medidor de consumo."""
    potencias = [-33_000.0] * 7 + [30_000.0] * 5
    ev = _evaluar_medidor(_medidor(), _lecturas(potencias), [], PUNTOS_5_MIN_EN_UNA_HORA)

    assert "S2" in ev["codigos"]


def test_p_negativa_aislada_no_activa_s2() -> None:
    """T9: un bucket negativo (~8%) no alcanza el 50% de buckets."""
    potencias = [-33_000.0] + [30_000.0] * 11
    ev = _evaluar_medidor(_medidor(), _lecturas(potencias), [], PUNTOS_5_MIN_EN_UNA_HORA)

    assert "S2" not in ev["codigos"]


def test_p_negativa_en_generacion_no_activa_s2() -> None:
    """S2 solo aplica a medidores de consumo: en generación la P negativa es lo esperado."""
    ev = _evaluar_medidor(
        _medidor(tipo_instalacion="GENERACION"), _lecturas([-33_000.0] * 12), [], PUNTOS_5_MIN_EN_UNA_HORA
    )

    assert "S2" not in ev["codigos"]


def test_alerta_de_polaridad_abierta_activa_s1_solo_en_su_medidor() -> None:
    """T6: alerta POLARIDAD_TI abierta en dev-1; dev-2 no se marca."""
    alertas = [{"dispositivo_id": "dev-1", "tipo_alerta": "POLARIDAD_TI", "categoria": "POLARIDAD_TI"}]

    ev_1 = _evaluar_medidor(_medidor(id="dev-1"), _lecturas([30_000.0] * 12), alertas, PUNTOS_5_MIN_EN_UNA_HORA)
    ev_2 = _evaluar_medidor(_medidor(id="dev-2"), _lecturas([30_000.0] * 12), alertas, PUNTOS_5_MIN_EN_UNA_HORA)

    assert "S1" in ev_1["codigos"]
    assert "S1" not in ev_2["codigos"]


def test_alerta_ti_invertido_por_categoria_tambien_activa_s1() -> None:
    alertas = [{"dispositivo_id": "dev-1", "tipo_alerta": "OTRA", "categoria": "TI_INVERTIDO"}]

    ev = _evaluar_medidor(_medidor(), _lecturas([30_000.0] * 12), alertas, PUNTOS_5_MIN_EN_UNA_HORA)

    assert "S1" in ev["codigos"]


def test_cobertura_baja_activa_s3_por_medidor() -> None:
    """T7: 6 de 12 buckets (50%) con dato."""
    ev = _evaluar_medidor(_medidor(), _lecturas([30_000.0] * 6), [], PUNTOS_5_MIN_EN_UNA_HORA)

    assert "S3" in ev["codigos"]
    assert ev["cobertura_puntos_pct"] == 50.0


def test_medidor_de_dos_fases_activa_s4_y_expone_la_fase_faltante() -> None:
    """T4: fases_con_ti = R,S; la fase T figura como faltante, no como cero."""
    ev = _evaluar_medidor(_medidor(fases_con_ti="R,S"), _lecturas([30_000.0] * 12), [], PUNTOS_5_MIN_EN_UNA_HORA)

    assert "S4" in ev["codigos"]
    assert ev["fases_medidas"] == ["R", "S"]
    assert ev["fases_faltantes"] == ["T"]


def test_resumen_marca_no_trifasico_sin_contar_la_fase_como_cero() -> None:
    evaluaciones = [
        _evaluar_medidor(_medidor(id="dev-1", fases_con_ti="R,S"), _lecturas([30_000.0] * 12), [], 12),
        _evaluar_medidor(_medidor(id="dev-2"), _lecturas([30_000.0] * 12), [], 12),
    ]

    resumen = _resumen_calidad(evaluaciones)

    assert resumen["total_trifasico_completo"] is False
    assert resumen["dispositivos_no_trifasicos"] == [{"dispositivo_id": "dev-1", "fases_faltantes": ["T"]}]
    assert [m["dispositivo_id"] for m in resumen["medidores_sospechosos"]] == ["dev-1"]


def test_bloquea_solo_con_s1_o_s2() -> None:
    """Decisión 7.1: S1 y S2 bloquean; S3 y S4 solo advierten."""
    solo_cobertura = _evaluar_medidor(_medidor(), _lecturas([30_000.0] * 6), [], 12)
    solo_fases = _evaluar_medidor(_medidor(fases_con_ti="R,S"), _lecturas([30_000.0] * 12), [], 12)
    con_inversion = _evaluar_medidor(_medidor(), _lecturas([-33_000.0] * 12), [], 12)

    assert _bloquea_calculo([solo_cobertura, solo_fases]) is False
    assert _bloquea_calculo([con_inversion]) is True


def test_muestra_truncada_no_calcula_s3_y_queda_no_verificable() -> None:
    """Ajuste de #31: 5000 lecturas (tope de limit) no son la ventana pedida. No se marca S3 ni 'sano'."""
    potencias = [30_000.0] * 5_000
    ev = _evaluar_medidor(_medidor(), _lecturas_largas(potencias), [], 8_640)

    assert ev["ventana_truncada"] is True
    assert ev["cobertura_estado"] == "no_verificable"
    assert ev["cobertura_puntos_pct"] is None
    assert "S3" not in ev["codigos"]


def test_muestra_completa_con_baja_cobertura_sigue_activando_s3() -> None:
    ev = _evaluar_medidor(_medidor(), _lecturas([30_000.0] * 6), [], PUNTOS_5_MIN_EN_UNA_HORA)

    assert ev["ventana_truncada"] is False
    assert ev["cobertura_estado"] == "verificada"
    assert "S3" in ev["codigos"]


def _lecturas_largas(potencias_w: list[float]) -> list[dict[str, Any]]:
    """Como _lecturas, pero sin límite de horas: una lectura cada 5 min desde 2026-10-01."""
    inicio = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return [
        {
            "registrado_en": (inicio + timedelta(minutes=5 * i)).isoformat().replace("+00:00", "Z"),
            "potencia_activa_total_W": p,
        }
        for i, p in enumerate(potencias_w)
    ]

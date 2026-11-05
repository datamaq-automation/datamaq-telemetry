"""tests/unit/test_correccion_angular_ti.py.

Pruebas del cálculo de corrección angular por fase (issue datamaq#29).

Usa el fixture del quiebre del Trafo 2 (medidor 369) del 2026-10-06. El corte de la rotación
vigente es el deploy ae8f46b, 2026-10-06 02:29:53 UTC: las filas de 02:25 son anteriores, las de
02:30 posteriores.

El fixture no tiene Q ni ángulo. Estas pruebas no fijan el signo de Q ni la polaridad: solo
verifican lo que V, I y P permiten afirmar.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.domain.telemetria.servicios.correccion_angular_ti import (
    alpha_para_objetivo,
    candidatos_angulo_bruto,
    magnitud_angulo_deg,
    normalizar_grados,
    potencia_activa_predicha,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ti" / "trafo2_369_quiebre_2026-10-06.csv"


def _filas() -> dict[str, dict[str, float]]:
    with FIXTURE.open(encoding="utf-8") as f:
        return {
            fila["recorded_at"][11:16]: {k: float(v) for k, v in fila.items() if k != "recorded_at"}
            for fila in csv.DictReader(f)
        }


def test_fixture_tiene_filas_antes_y_despues_del_corte():
    filas = _filas()
    assert "02:25" in filas and "02:30" in filas
    assert len(filas) == 27


def test_p_r_cambia_de_signo_en_el_corte():
    filas = _filas()
    assert filas["02:25"]["active_power_r"] > 0
    assert filas["02:30"]["active_power_r"] < 0


def test_magnitud_angulo_r_antes_y_despues_del_corte():
    f = _filas()
    antes = magnitud_angulo_deg(f["02:25"]["voltage_r"], f["02:25"]["current_r"], f["02:25"]["active_power_r"])
    despues = magnitud_angulo_deg(f["02:30"]["voltage_r"], f["02:30"]["current_r"], f["02:30"]["active_power_r"])
    assert antes == pytest.approx(30.2, abs=0.5)
    assert despues == pytest.approx(149.7, abs=0.5)


def test_magnitud_angulo_s_antes_y_despues_del_corte():
    f = _filas()
    antes = magnitud_angulo_deg(f["02:25"]["voltage_s"], f["02:25"]["current_s"], f["02:25"]["active_power_s"])
    despues = magnitud_angulo_deg(f["02:30"]["voltage_s"], f["02:30"]["current_s"], f["02:30"]["active_power_s"])
    assert antes == pytest.approx(30.5, abs=0.5)
    assert despues == pytest.approx(105.2, abs=0.5)


def test_magnitud_rechaza_potencia_aparente_no_positiva():
    with pytest.raises(ValueError):
        magnitud_angulo_deg(0.0, 170.0, 100.0)


def test_candidatos_r_quedan_con_dos_signos_porque_q_no_esta():
    # R: corrección R:180 antes del corte, R:0 después (decisión de datamaq-data y deploy ae8f46b).
    f = _filas()
    mag_antes = magnitud_angulo_deg(f["02:25"]["voltage_r"], f["02:25"]["current_r"], f["02:25"]["active_power_r"])
    mag_despues = magnitud_angulo_deg(f["02:30"]["voltage_r"], f["02:30"]["current_r"], f["02:30"]["active_power_r"])
    candidatos = candidatos_angulo_bruto(mag_antes, 180.0, mag_despues, 0.0)
    assert len(candidatos) == 2
    assert candidatos[0] == pytest.approx(-149.8, abs=0.5)
    assert candidatos[1] == pytest.approx(149.8, abs=0.5)


def test_candidatos_s_quedan_con_un_solo_valor():
    # S: corrección S:-120 antes del corte, S:15 después.
    f = _filas()
    mag_antes = magnitud_angulo_deg(f["02:25"]["voltage_s"], f["02:25"]["current_s"], f["02:25"]["active_power_s"])
    mag_despues = magnitud_angulo_deg(f["02:30"]["voltage_s"], f["02:30"]["current_s"], f["02:30"]["active_power_s"])
    candidatos = candidatos_angulo_bruto(mag_antes, -120.0, mag_despues, 15.0)
    assert len(candidatos) == 1
    assert candidatos[0] == pytest.approx(-90.0, abs=1.0)


def test_candidatos_r_dan_la_misma_potencia_activa_antes_del_corte():
    # Los dos candidatos de R predicen la misma P antes del corte: V, I y P no distinguen el signo de Q.
    f = _filas()
    s_antes = f["02:25"]["voltage_r"] * f["02:25"]["current_r"]
    mag_antes = magnitud_angulo_deg(f["02:25"]["voltage_r"], f["02:25"]["current_r"], f["02:25"]["active_power_r"])
    mag_despues = magnitud_angulo_deg(f["02:30"]["voltage_r"], f["02:30"]["current_r"], f["02:30"]["active_power_r"])
    candidatos = candidatos_angulo_bruto(mag_antes, 180.0, mag_despues, 0.0)
    potencias = [potencia_activa_predicha(s_antes, bruto, 180.0) for bruto in candidatos]
    assert potencias[0] == pytest.approx(potencias[1], rel=1e-6)
    assert potencias[0] == pytest.approx(f["02:25"]["active_power_r"], rel=0.01)


def test_potencia_predicha_s_con_candidato_unico_reproduce_el_fixture():
    f = _filas()
    s_antes = f["02:25"]["voltage_s"] * f["02:25"]["current_s"]
    potencia = potencia_activa_predicha(s_antes, -90.0, -120.0)
    assert potencia == pytest.approx(f["02:25"]["active_power_s"], rel=0.01)


def test_alpha_para_objetivo_reproduce_los_valores_de_la_convencion():
    # Convención A2: con bruto -90° en S y objetivo +30°, la corrección es S:-120.
    assert alpha_para_objetivo(-90.0, 30.0) == pytest.approx(-120.0)
    # Con bruto -150° en R, el mismo objetivo da R:180; con +150°, R:120. Ambos son candidatos.
    assert alpha_para_objetivo(-150.0, 30.0) == pytest.approx(180.0)
    assert alpha_para_objetivo(150.0, 30.0) == pytest.approx(120.0)


def test_normalizar_grados_al_intervalo_estandar():
    assert normalizar_grados(190.0) == pytest.approx(-170.0)
    assert normalizar_grados(-180.0) == pytest.approx(180.0)
    assert normalizar_grados(360.0) == pytest.approx(0.0)

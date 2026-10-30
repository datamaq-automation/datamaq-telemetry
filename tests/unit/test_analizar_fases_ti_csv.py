"""tests/unit/test_analizar_fases_ti_csv.py — Análisis por fase de un CSV con datos sintéticos (sin base, sin datos reales).

Caso A: fase S con TI invertido (ángulo V-I de -150° en S, +30° en R y T). Caso B: todo bien (+30° en las tres).
"""

import math

import pytest

from scripts.analizar_fases_ti_csv import diagnosticar

ANGULOS_V = {"R": 0.0, "S": -120.0, "T": 120.0}
ANGULOS_THETA_CORRECTO = {"R": 30.0, "S": 30.0, "T": 30.0}
ANGULOS_THETA_S_INVERTIDA = {"R": 30.0, "S": -150.0, "T": 30.0}


def _escribir_csv(ruta, thetas, con_q=True, instantes=30):
    lineas = ["timestamp,fase,V,I,P" + (",Q" if con_q else "")]
    for t in range(instantes):
        ts = f"2026-10-29T10:{t:02d}:00Z"
        for fase in ("R", "S", "T"):
            v = 230.0
            i = 10.0 + 0.1 * (t % 5)
            theta = math.radians(thetas[fase])
            p = v * i * math.cos(theta)
            q = v * i * math.sin(theta)
            fila = f"{ts},{fase},{v},{i:.2f},{p:.1f}"
            lineas.append(fila + (f",{q:.1f}" if con_q else ""))
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return ruta


def test_ti_invertido_en_s_se_distingue_de_r_y_t(tmp_path):
    ruta = _escribir_csv(tmp_path / "invertida.csv", ANGULOS_THETA_S_INVERTIDA)

    resultado = diagnosticar(ruta, ["R", "S", "T"])

    por_fase = resultado["por_fase"]
    assert por_fase["S"]["veredicto"].startswith("P_NEGATIVA")
    assert por_fase["S"]["fraccion_p_negativa"] == pytest.approx(1.0)
    assert por_fase["S"]["angulo_v_i_deg"] == pytest.approx(-150.0, abs=0.5)
    assert por_fase["R"]["veredicto"].startswith("P_POSITIVA")
    assert por_fase["T"]["veredicto"].startswith("P_POSITIVA")
    assert por_fase["R"]["angulo_v_i_deg"] == pytest.approx(30.0, abs=0.5)


def test_instalacion_correcta_no_marca_ninguna_fase(tmp_path):
    ruta = _escribir_csv(tmp_path / "correcta.csv", ANGULOS_THETA_CORRECTO)

    resultado = diagnosticar(ruta, ["R", "S", "T"])

    for fase in ("R", "S", "T"):
        assert resultado["por_fase"][fase]["veredicto"].startswith("P_POSITIVA")
        assert resultado["por_fase"][fase]["angulo_v_i_deg"] == pytest.approx(30.0, abs=0.5)


def test_con_q_se_reutiliza_el_ranking_existente(tmp_path):
    ruta = _escribir_csv(tmp_path / "con_q.csv", ANGULOS_THETA_CORRECTO)

    resultado = diagnosticar(ruta, ["R", "S", "T"])

    assert resultado["candidatos"], "el ranking de DiagnosticoTIService debe devolver candidatos"
    assert all({"orden", "invertido", "score"} <= set(c) for c in resultado["candidatos"])


def test_sin_q_no_hay_angulo_ni_ranking_pero_si_veredicto_de_potencia(tmp_path):
    ruta = _escribir_csv(tmp_path / "sin_q.csv", ANGULOS_THETA_S_INVERTIDA, con_q=False)

    resultado = diagnosticar(ruta, ["R", "S", "T"])

    assert resultado["candidatos"] == []
    assert resultado["por_fase"]["S"]["angulo_v_i_deg"] is None
    assert resultado["por_fase"]["S"]["veredicto"].startswith("P_NEGATIVA")


def test_ranking_empatado_se_declara_en_lugar_de_elegir(tmp_path, capsys):
    from scripts.analizar_fases_ti_csv import main

    ruta = _escribir_csv(tmp_path / "empate.csv", ANGULOS_THETA_S_INVERTIDA)

    assert main(["--csv", str(ruta), "--fases", "R,S,T"]) == 0
    salida = capsys.readouterr().out
    assert "Empate" in salida
    assert "Fase S" in salida

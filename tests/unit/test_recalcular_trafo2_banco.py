"""Tests del recálculo del Trafo 2 con R:-60,S:0 (datamaq-automation/datamaq#92)."""

from datetime import datetime, timedelta

import pytest

from scripts import recalcular_trafo2_banco as rt


def _fila_con_config(pr_raw, qr_raw, ps_raw, qs_raw, config="R180_S-120", **extra):
    """Fila tal como la guarda el medidor: P' y Q' rotadas con la configuración aplicada."""
    cfg = rt.CONFIGURACIONES[config]
    pr, qr = rt.rotar(pr_raw, qr_raw, cfg["R"])
    ps, qs = rt.rotar(ps_raw, qs_raw, cfg["S"])
    fila = {
        "id": "1",
        "device_id": rt.DISPOSITIVO_ID,
        "recorded_at": "2026-10-01 04:50:00",
        "active_power_r": f"{pr:.2f}",
        "reactive_power_r": f"{qr:.2f}",
        "power_factor_r": "0.86",
        "apparent_power_r": "39721.00",
        "active_power_s": f"{ps:.2f}",
        "reactive_power_s": f"{qs:.2f}",
        "power_factor_s": "0.85",
        "apparent_power_s": "41089.58",
        "total_active_power": f"{pr + ps:.2f}",
        "total_reactive_power": f"{qr + qs:.2f}",
        "total_apparent_power": "80810.58",
        "total_power_factor": "0.85",
    }
    fila.update(extra)
    return fila


def test_deshacer_es_la_inversa_de_rotar():
    p, q = rt.rotar(12345.0, -678.0, -60.0)
    p_raw, q_raw = rt.deshacer(p, q, -60.0)
    assert p_raw == pytest.approx(12345.0)
    assert q_raw == pytest.approx(-678.0)


def test_identificar_reconoce_la_configuracion_con_crudo_entero():
    fila = _fila_con_config(34000, 19000, 34500, 19500, config="R180_S-120")
    config, estado = rt.identificar(
        float(fila["active_power_r"]),
        float(fila["reactive_power_r"]),
        float(fila["active_power_s"]),
        float(fila["reactive_power_s"]),
    )
    assert (config, estado) == ("R180_S-120", "ok")


def test_identificar_marca_ambigua_cuando_dos_configuraciones_dan_enteros():
    # P y Q nulas: cualquier rotación da enteros, así que no hay identificación única.
    config, estado = rt.identificar(0.0, 0.0, 0.0, 0.0)
    assert config is None
    assert estado == "ambigua"


def test_recalcular_fila_pasa_del_crudo_a_r_menos60_s0():
    pr_raw, qr_raw, ps_raw, qs_raw = 30000.0, 20000.0, 35000.0, 19000.0
    fila = _fila_con_config(pr_raw, qr_raw, ps_raw, qs_raw, config="R180_S-120")

    nuevo = rt.recalcular_fila(fila, "R180_S-120")

    pr_esp, qr_esp = rt.rotar(pr_raw, qr_raw, -60.0)
    assert nuevo["active_power_r"] == pytest.approx(round(pr_esp, 2), abs=0.01)
    assert nuevo["reactive_power_r"] == pytest.approx(round(qr_esp, 2), abs=0.01)
    # S se rota 0°: queda el crudo.
    assert nuevo["active_power_s"] == pytest.approx(ps_raw, abs=0.01)
    assert nuevo["reactive_power_s"] == pytest.approx(qs_raw, abs=0.01)
    # Totales = suma de fases; la aparente total no cambia.
    assert nuevo["total_active_power"] == pytest.approx(round(pr_esp + ps_raw, 2), abs=0.01)
    assert nuevo["total_reactive_power"] == pytest.approx(round(qr_esp + qs_raw, 2), abs=0.01)


def test_recalcular_fila_recalcula_fp_con_la_aparente_guardada():
    fila = _fila_con_config(30000.0, 20000.0, 35000.0, 19000.0)
    nuevo = rt.recalcular_fila(fila, "R180_S-120")
    assert nuevo["power_factor_r"] == round(nuevo["active_power_r"] / 39721.0, 2)
    assert nuevo["total_power_factor"] == round(nuevo["total_active_power"] / 80810.58, 2)


def test_recalcular_fila_conserva_fp_si_falta_la_aparente():
    fila = _fila_con_config(30000.0, 20000.0, 35000.0, 19000.0, apparent_power_r=None)
    nuevo = rt.recalcular_fila(fila, "R180_S-120")
    assert nuevo["power_factor_r"] == 0.86


def test_procesar_instantanea_omite_filas_ya_corregidas_y_fuera_de_ventana():
    ya = _fila_con_config(30000.0, 20000.0, 35000.0, 19000.0, config="R-60_S0")
    ya["id"] = "2"
    antes = _fila_con_config(30000.0, 20000.0, 35000.0, 19000.0, config="R180_S-120")
    antes["recorded_at"] = "2026-09-20 10:00:00"
    antes["id"] = "3"
    procesadas = rt.procesar_instantanea([ya, antes], "2026-09-26 00:00:00", None)
    assert [p["estado"] for p in procesadas] == ["ya_corregida"]


def test_procesar_instantanea_aplica_filas_de_configuracion_conocida():
    fila = _fila_con_config(30000.0, 20000.0, 35000.0, 19000.0)
    procesadas = rt.procesar_instantanea([fila], "2026-09-26 00:00:00", None)
    assert procesadas[0]["estado"] == "aplicar"
    assert procesadas[0]["config"] == "R180_S-120"


def test_acumulado_trapecio_con_potencia_constante_da_un_kwh_por_hora():
    t0 = datetime(2026, 10, 1, 0, 0, 0)
    tiempos = [t0 + timedelta(minutes=5 * i) for i in range(13)]  # 1 hora
    acum = rt.Acumulado(t0, 100.0, tiempos, [1000.0] * len(tiempos))
    assert acum.en(tiempos[-1]) == pytest.approx(101.0)


def test_acumulado_interpola_linealmente_dentro_de_un_intervalo():
    t0 = datetime(2026, 10, 1, 0, 0, 0)
    tiempos = [t0, t0 + timedelta(hours=1)]
    acum = rt.Acumulado(t0, 0.0, tiempos, [0.0, 2000.0])  # rampa 0 → 2 kW en 1 h: 1 kWh total
    medio = t0 + timedelta(minutes=30)
    # Se interpola el acumulado linealmente entre bordes: a mitad de intervalo, la mitad del tramo.
    assert acum.en(medio) == pytest.approx(0.5)
    assert acum.en(tiempos[-1]) == pytest.approx(1.0)


def test_hueco_mayor_a_15_min_se_detecta():
    t0 = datetime(2026, 10, 12, 4, 0, 0)
    muestras = [
        rt.Muestra(t=t0, p_raw=0, q_raw=0, p_corr=0, q_corr=0),
        rt.Muestra(t=t0 + timedelta(minutes=74), p_raw=0, q_raw=0, p_corr=0, q_corr=0),
    ]
    assert rt.huecos(muestras) == [(t0, t0 + timedelta(minutes=74), 74.0)]


def test_sql_aplicar_guarda_sobre_valores_viejos_y_reversion_restaura_originales():
    fila = _fila_con_config(30000.0, 20000.0, 35000.0, 19000.0)
    nuevo = rt.recalcular_fila(fila, "R180_S-120")
    item = {"fila": fila, "nuevo": nuevo, "estado": "aplicar", "config": "R180_S-120"}

    aplicar = rt.sql_instantanea([item], revertir=False)
    revertir = rt.sql_instantanea([item], revertir=True)

    assert aplicar.startswith("UPDATE telemetry_instantaneous SET")
    assert f"WHERE id = 1 AND active_power_r <=> {fila['active_power_r']}" in aplicar
    assert f"active_power_r = {nuevo['active_power_r']:.6f}" in aplicar
    assert f"active_power_r = {fila['active_power_r']}" in revertir
    assert f"WHERE id = 1 AND active_power_r <=> {nuevo['active_power_r']:.6f}" in revertir


def test_envolver_transaccion_declara_filas_esperadas_y_commit():
    sql = rt.envolver_transaccion("UPDATE x SET a = 1 WHERE id = 1;\n", "prueba", 1)
    assert "START TRANSACTION;" in sql
    assert "Filas esperadas: 1" in sql
    assert sql.rstrip().endswith("COMMIT;")


def test_leer_respaldo_solo_toma_el_dispositivo_y_no_lee_usuarios(tmp_path):
    ruta = tmp_path / "respaldo.sql"
    ruta.write_text(
        "CREATE TABLE `telemetry_energy` (\n"
        "  `id` bigint NOT NULL AUTO_INCREMENT,\n"
        "  `device_id` varchar(36) NOT NULL,\n"
        "  `recorded_at` datetime NOT NULL,\n"
        "  `source` varchar(16) DEFAULT NULL,\n"
        "  PRIMARY KEY (`id`)\n"
        ") ENGINE=InnoDB;\n"
        f"INSERT INTO `telemetry_energy` VALUES (7,'{rt.DISPOSITIVO_ID}','2026-10-01 00:00:00','acc'),"
        "(8,'otro-dispositivo','2026-10-01 00:00:00','acc');\n"
        "INSERT INTO `users` VALUES (1,'secreto');\n",
        encoding="utf-8",
    )
    instant, energia = rt.leer_respaldo(ruta)
    assert instant == []
    assert [e["id"] for e in energia] == ["7"]

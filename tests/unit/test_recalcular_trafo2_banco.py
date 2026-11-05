"""tests/unit/test_recalcular_trafo2_banco.py.

Tests del recálculo del Trafo 2 con R:-60,S:0 (datamaq-automation/datamaq#92)."""

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


def _energia(id_, recorded_at, neta, reactiva):
    return {
        "id": str(id_),
        "device_id": rt.DISPOSITIVO_ID,
        "recorded_at": recorded_at,
        "net_active_energy_kwh": f"{neta:.3f}",
        "imported_active_energy_kwh": f"{neta:.3f}",
        "exported_active_energy_kwh": None,
        "net_reactive_energy_kvarh": f"{reactiva:.3f}",
        "imported_reactive_energy_kvarh": f"{reactiva:.3f}",
        "exported_reactive_energy_kvarh": None,
        "source": "acc",
    }


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
    # Totales = suma de fases.
    assert nuevo["total_active_power"] == pytest.approx(round(pr_esp + ps_raw, 2), abs=0.01)
    assert nuevo["total_reactive_power"] == pytest.approx(round(qr_esp + qs_raw, 2), abs=0.01)


def test_recalcular_fila_recalcula_fp_con_la_aparente_guardada():
    fila = _fila_con_config(30000.0, 20000.0, 35000.0, 19000.0)
    nuevo = rt.recalcular_fila(fila, "R180_S-120")
    assert nuevo["power_factor_r"] == round(float(nuevo["active_power_r"] or 0) / 39721.0, 2)
    assert nuevo["total_power_factor"] == round(float(nuevo["total_active_power"] or 0) / 80810.58, 2)


def test_recalcular_fila_conserva_fp_si_falta_la_aparente():
    fila = _fila_con_config(30000.0, 20000.0, 35000.0, 19000.0, apparent_power_r=None)
    nuevo = rt.recalcular_fila(fila, "R180_S-120")
    assert nuevo["power_factor_r"] == 0.86


def test_procesar_instantanea_omite_filas_ya_corregidas_y_anteriores_a_desde():
    ya = _fila_con_config(30000.0, 20000.0, 35000.0, 19000.0, config="R-60_S0")
    ya["id"] = "2"
    antes = _fila_con_config(30000.0, 20000.0, 35000.0, 19000.0, config="R180_S-120")
    antes["recorded_at"] = "2026-09-20 10:00:00"
    antes["id"] = "3"
    procesadas = rt.procesar_instantanea([ya, antes], "2026-09-26 00:00:00")
    assert [p["estado"] for p in procesadas] == ["ya_corregida"]


def test_procesar_instantanea_aplica_filas_de_configuracion_conocida():
    fila = _fila_con_config(30000.0, 20000.0, 35000.0, 19000.0)
    procesadas = rt.procesar_instantanea([fila], "2026-09-26 00:00:00")
    assert procesadas[0]["estado"] == "aplicar"
    assert procesadas[0]["config"] == "R180_S-120"


def test_acumulado_trapecio_con_potencia_constante_da_un_kwh_por_hora():
    t0 = datetime(2026, 10, 1, 0, 0, 0)
    tiempos = [t0 + timedelta(minutes=5 * i) for i in range(13)]  # 1 hora
    acum = rt.Acumulado(tiempos, [1000.0] * len(tiempos))
    assert acum.en(tiempos[-1]) == pytest.approx(1.0)


def test_acumulado_interpola_linealmente_dentro_de_un_intervalo():
    t0 = datetime(2026, 10, 1, 0, 0, 0)
    tiempos = [t0, t0 + timedelta(hours=1)]
    acum = rt.Acumulado(tiempos, [0.0, 2000.0])  # rampa 0 → 2 kW en 1 h: 1 kWh total
    # Se interpola el acumulado linealmente entre bordes: a mitad de intervalo, la mitad del tramo.
    assert acum.en(t0 + timedelta(minutes=30)) == pytest.approx(0.5)
    assert acum.en(tiempos[-1]) == pytest.approx(1.0)


def test_energia_se_ancla_al_final_y_la_ultima_fila_no_cambia():
    t_desde = "2026-09-26 00:00:00"
    muestras = [
        rt.Muestra(t=datetime(2026, 9, 26, 0, 0, 0), p_raw=0, q_raw=0, p_corr=1000.0, q_corr=0.0),
        rt.Muestra(t=datetime(2026, 9, 26, 1, 0, 0), p_raw=0, q_raw=0, p_corr=1000.0, q_corr=0.0),
    ]
    energia = [
        _energia(1, "2026-09-25 23:55:00", 10.0, 0.0),  # pre: se desplaza
        _energia(2, "2026-09-26 00:00:00", 20.0, 0.0),
        _energia(3, "2026-09-26 01:00:00", 21.0, 0.0),  # T: última fila del medidor
    ]
    filas, controles = rt.recalcular_energia(energia, muestras, t_desde, "2026-09-25 00:00:00")
    por_id = {f["id"]: f for f in filas}

    # T no cambia.
    assert por_id["3"]["despues"]["net_active_energy_kwh"] == pytest.approx(21.0)
    # Primera integrada: 21 - 1 kWh (una hora a 1 kW).
    assert por_id["2"]["despues"]["net_active_energy_kwh"] == pytest.approx(20.0)
    # Pre: se conserva su diferencia medida y se desplaza la misma constante que la primera integrada (0).
    assert por_id["1"]["despues"]["net_active_energy_kwh"] == pytest.approx(10.0)
    assert por_id["1"]["marca"] == "pre_desplazada"
    assert controles["fila_final"]["recalculado_kwh"] == pytest.approx(21.0)
    assert controles["max_abs_dif_delta_vs_integral_kwh"] == pytest.approx(0.0, abs=1e-9)


def test_energia_desplaza_pre_y_empalma_con_la_diferencia_medida():
    t_desde = "2026-09-26 00:00:00"
    muestras = [
        rt.Muestra(t=datetime(2026, 9, 26, 0, 0, 0), p_raw=0, q_raw=0, p_corr=2000.0, q_corr=0.0),
        rt.Muestra(t=datetime(2026, 9, 26, 1, 0, 0), p_raw=0, q_raw=0, p_corr=2000.0, q_corr=0.0),
    ]
    energia = [
        _energia(1, "2026-09-25 23:55:00", 100.0, 0.0),
        _energia(2, "2026-09-26 00:00:00", 100.5, 0.0),  # el medidor avanzó 0,5 kWh en el empalme
        _energia(3, "2026-09-26 01:00:00", 102.5, 0.0),
    ]
    filas, controles = recalcular_energia_para_test(energia, muestras, t_desde)
    por_id = {f["id"]: f for f in filas}
    # Primera integrada = 102,5 - 2 kWh = 100,5 (empalme exacto con el medidor).
    assert por_id["2"]["despues"]["net_active_energy_kwh"] == pytest.approx(100.5)
    # La pre conserva su distancia medida a la primera integrada: no hay salto artificial.
    assert por_id["1"]["despues"]["net_active_energy_kwh"] == pytest.approx(100.0)
    assert controles["empalme"]["salto_kwh"] == pytest.approx(0.5)


def recalcular_energia_para_test(energia, muestras, t_desde):
    return rt.recalcular_energia(energia, muestras, t_desde, "2026-09-25 00:00:00")


def test_control_de_saltos_reporta_maximo_y_no_supera_margen_en_serie_consistente():
    t0 = datetime(2026, 9, 26, 0, 0, 0)
    muestras = [
        rt.Muestra(t=t0 + timedelta(minutes=5 * i), p_raw=0, q_raw=0, p_corr=1200.0, q_corr=0.0) for i in range(13)
    ]
    energia = [
        _energia(i, (t0 + timedelta(minutes=5 * i)).strftime("%Y-%m-%d %H:%M:%S"), 50.0 + i / 10, 0.0)
        for i in range(13)
    ]
    _, controles = rt.recalcular_energia(energia, muestras, "2026-09-26 00:00:00", "2026-09-25 00:00:00")
    assert controles["pares_sobre_margen"] == 0
    assert controles["max_abs_dif_delta_vs_integral_kwh"] < 0.01


def test_hueco_mayor_a_15_min_se_detecta():
    t0 = datetime(2026, 10, 12, 4, 0, 0)
    muestras = [
        rt.Muestra(t=t0, p_raw=0, q_raw=0, p_corr=0, q_corr=0),
        rt.Muestra(t=t0 + timedelta(minutes=74), p_raw=0, q_raw=0, p_corr=0, q_corr=0),
    ]
    assert rt.huecos(muestras) == [(t0, t0 + timedelta(minutes=74), 74.0)]


def test_sql_aplicar_guarda_sobre_valores_viejos_y_device_y_reversion_restaura_originales():
    fila = _fila_con_config(30000.0, 20000.0, 35000.0, 19000.0)
    nuevo = rt.recalcular_fila(fila, "R180_S-120")
    item = {"fila": fila, "nuevo": nuevo, "estado": "aplicar", "config": "R180_S-120"}

    aplicar = rt.sql_instantanea([item], revertir=False)
    revertir = rt.sql_instantanea([item], revertir=True)

    guarda_device = f"device_id = '{rt.DISPOSITIVO_ID}'"
    assert aplicar.startswith("UPDATE telemetry_instantaneous SET")
    assert f"WHERE id = 1 AND {guarda_device} AND active_power_r <=> {fila['active_power_r']}" in aplicar
    assert f"active_power_r = {nuevo['active_power_r']:.6f}" in aplicar
    assert f"active_power_r = {fila['active_power_r']}" in revertir
    assert f"WHERE id = 1 AND {guarda_device} AND active_power_r <=> {nuevo['active_power_r']:.6f}" in revertir


def test_sql_energia_lleva_guarda_de_device():
    fila = _energia(7, "2026-09-26 00:00:00", 100.0, 0.0)
    item = {
        "id": "7",
        "antes": {c: fila[c] for c in rt.COLUMNAS_ENERGIA},
        "despues": {c: 101.0 for c in rt.COLUMNAS_ENERGIA},
    }
    sql = rt.sql_energia([item], revertir=False)
    assert f"device_id = '{rt.DISPOSITIVO_ID}'" in sql
    assert "WHERE id = 7" in sql


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


def test_leer_tabla_exportada_tsv_con_nulos_y_filtro_de_device(tmp_path):
    ruta = tmp_path / "energia.tsv"
    ruta.write_text(
        "id\tdevice_id\trecorded_at\tnet_active_energy_kwh\tsource\n"
        f"7\t{rt.DISPOSITIVO_ID}\t2026-10-01 00:00:00\t12.500\tacc\n"
        f"8\t{rt.DISPOSITIVO_ID}\t2026-10-01 00:05:00\tNULL\tacc\n"
        "9\totro\t2026-10-01 00:00:00\t1.000\tacc\n",
        encoding="utf-8",
    )
    filas = rt.leer_tabla_exportada(ruta)
    assert [f["id"] for f in filas] == ["7", "8"]
    assert filas[1]["net_active_energy_kwh"] is None


def test_leer_tabla_exportada_csv(tmp_path):
    ruta = tmp_path / "instantanea.csv"
    ruta.write_text(
        f"id,device_id,recorded_at,active_power_r\n1,{rt.DISPOSITIVO_ID},2026-10-01 00:00:00,-341.77\n",
        encoding="utf-8",
    )
    filas = rt.leer_tabla_exportada(ruta)
    assert filas == [
        {"id": "1", "device_id": rt.DISPOSITIVO_ID, "recorded_at": "2026-10-01 00:00:00", "active_power_r": "-341.77"}
    ]


def test_ya_corregida_integra_el_valor_almacenado_sin_volver_a_rotar():
    # Fila posterior al reinicio: ya está en R:-60,S:0 y se genera desde un crudo entero.
    fila = _fila_con_config(30000.0, 20000.0, 35000.0, 19000.0, config="R-60_S0")
    fila["recorded_at"] = "2026-10-30 01:00:00"
    procesadas = rt.procesar_instantanea([fila], "2026-09-26 00:00:00")
    assert procesadas[0]["estado"] == "ya_corregida"

    (muestra,) = rt.muestras_desde_filas(procesadas)

    assert muestra.p_corr == pytest.approx(float(fila["active_power_r"]) + float(fila["active_power_s"]), abs=1e-9)
    assert muestra.q_corr == pytest.approx(float(fila["reactive_power_r"]) + float(fila["reactive_power_s"]), abs=1e-9)


def test_fila_de_energia_que_cruza_una_muestra_ambigua_queda_marcada():
    t0 = datetime(2026, 9, 26, 0, 0, 0)
    muestras = [
        rt.Muestra(t=t0, p_raw=0, q_raw=0, p_corr=1000.0, q_corr=0.0),
        rt.Muestra(t=t0 + timedelta(minutes=15), p_raw=0, q_raw=0, p_corr=1000.0, q_corr=0.0),
    ]
    energia = [
        _energia(1, "2026-09-26 00:00:00", 20.0, 0.0),
        _energia(2, "2026-09-26 00:07:30", 20.125, 0.0),
        _energia(3, "2026-09-26 00:15:00", 20.25, 0.0),
    ]
    ambigua = [
        t0 + timedelta(minutes=8)
    ]  # no entra en la integral: queda entre las muestras 00:00 y 00:15  # no entra en la integral: la serie se interpola entre vecinas
    filas, _ = rt.recalcular_energia(energia, muestras, "2026-09-26 00:00:00", "2026-09-25 00:00:00", ambiguas=ambigua)
    marcas = {f["id"]: f["marca"] for f in filas}
    assert marcas["2"] == "interpolada_ambigua"
    assert marcas["1"] == "integrada"

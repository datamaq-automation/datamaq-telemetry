"""tests/unit/test_resumen_logs_vps.py — Tests unitarios de scripts/resumen_logs_vps.py (sin VPS)."""

import json

from scripts.resumen_logs_vps import normalizar_uri, resumir


def _entrada_json(evento, nivel, **campos):
    payload = {"event": evento, "level": nivel, **campos}
    return {"MESSAGE": json.dumps(payload)}


def _entrada_texto(msg):
    return {"MESSAGE": msg}


def test_telemetria_desglosa_alerta_por_tipo_mqtt_por_topico_y_404_por_path():
    entradas = [
        _entrada_json("alerta_calidad_energia_detectada", "warning", tipo="SOBRETENSION"),
        _entrada_json("alerta_calidad_energia_detectada", "warning", tipo="SOBRETENSION"),
        _entrada_json("alerta_calidad_energia_detectada", "warning", tipo="BAJO_FACTOR_POTENCIA"),
        _entrada_json("mqtt_mensaje_duplicado", "warning", topico="m/wifi/AAA/acc"),
        _entrada_json("ruta_no_encontrada", "warning", path="/api/graphql", ip="10.0.0.1"),
    ]
    salida = resumir(entradas, "datamaq-telemetry", es_json=True)
    assert "alerta_calidad_energia_detectada: 3" in salida
    assert "tipo=SOBRETENSION: 2" in salida
    assert "tipo=BAJO_FACTOR_POTENCIA: 1" in salida
    assert "topico=m/wifi/AAA/acc: 1" in salida
    assert "path=/api/graphql: 1" in salida
    # la IP del cliente no se imprime
    assert "10.0.0.1" not in salida


def test_errores_json_cuentan_como_errores():
    entradas = [_entrada_json("fallo_x", "error"), _entrada_json("fallo_y", "critical")]
    salida = resumir(entradas, "datamaq-telemetry", es_json=True)
    assert "errores: 2" in salida


def test_isftn_separa_csp_de_otros_warnings_y_agrupa_cloudflare():
    csp = {
        "csp-report": {
            "blocked-uri": "https://static.cloudflareinsights.com/beacon.min.js/vce70abc",
            "violated-directive": "script-src-elem",
        }
    }
    entradas = [
        _entrada_texto("2026-10-27T10:00:00 WARNING app: Violación CSP reportada: " + json.dumps(csp)),
        _entrada_texto("2026-10-27T10:00:01 WARNING app: Violación CSP reportada: " + json.dumps(csp)),
        _entrada_texto("2026-10-27T10:00:02 WARNING app: cache miss 17"),
        _entrada_texto("2026-10-27T10:00:03 ERROR app: boom"),
    ]
    salida = resumir(entradas, "isftn199", es_json=False)
    assert "warnings CSP (Content-Security-Policy): 2" in salida
    assert "blocked-uri https://static.cloudflareinsights.com/beacon.min.js: 2" in salida
    assert "otros warnings de texto: 1" in salida
    assert "errores: 1" in salida


def test_csp_con_json_roto_no_rompe_el_resumen():
    entradas = [_entrada_texto("WARNING app: Violación CSP reportada: {no-json}")]
    salida = resumir(entradas, "isftn199", es_json=False)
    assert "sin detalle parseable: 1" in salida


def test_modo_plano_sin_sangrias_ni_marco():
    entradas = [_entrada_json("ruta_no_encontrada", "warning", path="/x")]
    salida = resumir(entradas, "datamaq-telemetry", es_json=True, plano=True)
    lineas = salida.splitlines()
    assert lineas[0] == "datamaq-telemetry (últimas 24 h)"
    assert all(not linea.startswith(" ") or linea.startswith("  - ") for linea in lineas)
    assert "==" not in salida
    assert "- path=/x: 1" in salida


def test_normalizar_uri_quita_version_de_recurso_js():
    assert normalizar_uri("https://x.test/beacon.min.js/vce701abc") == "https://x.test/beacon.min.js"
    assert normalizar_uri("wasm-eval") == "wasm-eval"

#!/usr/bin/env python3
"""Desglose de 24 h de los logs journald del VPS, por servicio y por evento.

Lee por stdin la salida de `journalctl -u <unidad> -o json` (la trae
`scripts/resumen_logs_vps.sh` por ssh, solo lectura) y escribe un bloque de texto.
Criterio de clasificación igual que `/usr/local/bin/alertas-logs.py` (resumen()).

Uso (lo invoca el wrapper, no a mano):
    journalctl -u isftn199.service -o json | python3 -I scripts/resumen_logs_vps.py --unit isftn199.service
"""

import argparse
import json
import re
import sys
from collections import Counter

ANSI = re.compile(r"\x1b\[[0-9;]*m")
TEXTO_ERROR = re.compile(r"^(?:\S+\s+)?(ERROR|CRITICAL|Traceback)\b")
TEXTO_WARNING = re.compile(r"^(?:\S+\s+)?WARNING\b")
CSP = re.compile(r"Violación CSP reportada: (\{.*\})")

# unidad systemd -> nombre corto y si loguea JSON de structlog (como alertas-logs.py).
UNIDADES = {
    "datamaq-telemetry.service": {"nombre": "datamaq-telemetry", "json": True},
    "isftn199.service": {"nombre": "isftn199", "json": False},
    "eitec.service": {"nombre": "eitec", "json": False},
    "cybersyn.service": {"nombre": "cybersyn", "json": False},
}

# Evento de warning JSON -> campo por el que se desglosa.
DESGLOSE = {
    "alerta_calidad_energia_detectada": "tipo",
    "mqtt_mensaje_duplicado": "topico",
    "ruta_no_encontrada": "path",
}


def mensaje(entrada):
    msg = entrada.get("MESSAGE", "")
    if isinstance(msg, list):
        # journald exporta como array de bytes los mensajes con caracteres de control
        msg = bytes(msg).decode("utf-8", "replace")
    return msg if isinstance(msg, str) else ""


def parse_json(msg):
    try:
        d = json.loads(msg)
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def normalizar(texto):
    """Agrupa mensajes de texto: los números no separan grupos."""
    return re.sub(r"\d+", "N", texto)[:90]


def normalizar_uri(uri):
    """Quita el sufijo de versión de un recurso (beacon.min.js/vce70…) para agrupar."""
    return re.sub(r"(\.js)/\S*$", r"\1", uri)


def clasificar(entradas, es_json):
    """Cuenta errores y warnings de las entradas de una unidad."""
    res = {
        "errores": 0,
        "eventos": Counter(),  # warning JSON por evento
        "desglose": {},  # evento -> Counter(valor del campo)
        "csp": Counter(),  # warning CSP por blocked-uri
        "csp_sin_detalle": 0,
        "otros": Counter(),  # warning de texto, normalizado
    }
    for entrada in entradas:
        msg = ANSI.sub("", mensaje(entrada))
        if es_json:
            d = parse_json(msg)
            if d is not None:
                nivel = str(d.get("level", "")).lower()
                evento = d.get("event", "?")
                if nivel in ("error", "critical", "exception") or "exception" in d:
                    res["errores"] += 1
                elif nivel == "warning":
                    res["eventos"][evento] += 1
                    if evento in DESGLOSE:
                        valor = str(d.get(DESGLOSE[evento], "?"))
                        res["desglose"].setdefault(evento, Counter())[valor] += 1
                continue
        if TEXTO_ERROR.match(msg):
            res["errores"] += 1
        elif TEXTO_WARNING.match(msg):
            m = CSP.search(msg)
            if m:
                try:
                    uri = json.loads(m.group(1)).get("csp-report", {}).get("blocked-uri", "?")
                except (ValueError, AttributeError):
                    res["csp_sin_detalle"] += 1
                    continue
                res["csp"][normalizar_uri(str(uri))] += 1
            else:
                res["otros"][normalizar(msg)] += 1
    return res


def formatear(nombre, res, plano, top):
    """Texto del bloque de un servicio. Plano: sin sangría ni marco (Telegram)."""

    def linea(nivel, texto):
        if plano:
            return {1: "", 2: "- ", 3: "  - "}[nivel] + texto
        return "  " * nivel + texto

    lineas = [f"{nombre} (últimas 24 h)"] if plano else [f"== {nombre} (últimas 24 h) =="]
    lineas.append(linea(1, f"errores: {res['errores']}"))

    if res["eventos"]:
        lineas.append(linea(1, "warnings JSON por evento:"))
        for evento, n in res["eventos"].most_common(top):
            lineas.append(linea(2, f"{evento}: {n}"))
            if evento in res["desglose"]:
                campo = DESGLOSE[evento]
                for valor, k in res["desglose"][evento].most_common(top):
                    lineas.append(linea(3, f"{campo}={valor}: {k}"))

    total_csp = sum(res["csp"].values()) + res["csp_sin_detalle"]
    if total_csp:
        lineas.append(linea(1, f"warnings CSP (Content-Security-Policy): {total_csp}"))
        for uri, n in res["csp"].most_common(top):
            lineas.append(linea(2, f"blocked-uri {uri}: {n}"))
        if res["csp_sin_detalle"]:
            lineas.append(linea(2, f"sin detalle parseable: {res['csp_sin_detalle']}"))

    total_otros = sum(res["otros"].values())
    if total_otros:
        lineas.append(linea(1, f"otros warnings de texto: {total_otros}"))
        for texto, n in res["otros"].most_common(top):
            lineas.append(linea(2, f"{texto}: {n}"))

    return "\n".join(lineas)


def resumir(entradas, nombre, es_json, plano=False, top=10):
    return formatear(nombre, clasificar(entradas, es_json), plano, top)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Resumen 24 h de logs journald (stdin: journalctl -o json).")
    parser.add_argument("--unit", required=True, choices=sorted(UNIDADES))
    parser.add_argument("--plano", action="store_true", help="texto sin sangrías ni marcos (cuerpo de Telegram)")
    parser.add_argument("--top", type=int, default=10, help="máximo de grupos por sección")
    args = parser.parse_args(argv)

    entradas = []
    for linea in sys.stdin:
        try:
            entradas.append(json.loads(linea))
        except ValueError:
            continue
    info = UNIDADES[args.unit]
    print(resumir(entradas, info["nombre"], info["json"], args.plano, args.top))


if __name__ == "__main__":
    main()

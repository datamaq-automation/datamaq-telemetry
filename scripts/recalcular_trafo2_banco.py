#!/usr/bin/env python3
"""Recalcula el Trafo 2 de San Martín (medidor 369) con la corrección R:-60,S:0.

Decisión: decisions/2026-10-29_correccion-angular-trafo2-banco-fijo.md (D2 potencia
instantánea y D3 energía). Issue: datamaq-automation/datamaq#92.

Método: el medidor reporta P y Q enteros. Por eso el ángulo que se aplicó a cada fila se
identifica deshaciendo cada configuración conocida y comprobando que el resultado sea
entero (tolerancia 0,02). El signo de R no lo da el test (0° y 180° dan enteros), así que
la configuración se decide con R y S juntos. Con el crudo recuperado se rota con
R:-60,S:0 y se recalculan P, Q y FP de R y S, y los totales. V, I y la aparente por fase
no cambian.

La energía (telemetry_energy, source='acc') se reemplaza por el acumulado trapezoidal de
la potencia corregida, con interpolación lineal en cada recorded_at. Los huecos de más de
15 min se cruzan con trapecio y quedan marcados.

Nunca se conecta a una base. El SQL lo ejecuta DevOps.

Uso:
  python3 scripts/recalcular_trafo2_banco.py --en-seco
  python3 scripts/recalcular_trafo2_banco.py --generar-sql --desde 2026-09-26 --hasta 2026-10-06
"""

from __future__ import annotations

import argparse
import bisect
import csv
import itertools
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]

DISPOSITIVO_ID = "c91713f1-0621-4a33-9279-c5327a317d96"
DESDE_DEFAULT = "2026-09-26 00:00:00"
RESPALDO_DEFAULT = RAIZ / "tmp" / "2026-10-29" / "telemetry.sql"
SALIDA_DEFAULT = RAIZ / "tmp" / "2026-10-29_issue-92"

DESTINO: dict[str, float] = {"R": -60.0, "S": 0.0}
CONFIGURACIONES: dict[str, dict[str, float]] = {
    "R180_S-120": {"R": 180.0, "S": -120.0},
    "R0_S15": {"R": 0.0, "S": 15.0},
    "R-60_S0": {"R": -60.0, "S": 0.0},
}
TOLERANCIA = 0.02
HUECO_MIN = 15.0
FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"
COLUMNAS_POTENCIA = [
    "active_power_r",
    "reactive_power_r",
    "power_factor_r",
    "active_power_s",
    "reactive_power_s",
    "power_factor_s",
    "total_active_power",
    "total_reactive_power",
    "total_power_factor",
]
COLUMNAS_ENERGIA = [
    "net_active_energy_kwh",
    "imported_active_energy_kwh",
    "net_reactive_energy_kvarh",
    "imported_reactive_energy_kvarh",
]
UTC_LOCAL = timezone(timedelta(hours=-3))

Fila = dict[str, Any]


# --- Álgebra fasorial -------------------------------------------------------------------


def rotar(p: float, q: float, grados: float) -> tuple[float, float]:
    """Misma convención que rotar_fase_fasorial: P' = P·cos a + Q·sin a; Q' = Q·cos a - P·sin a."""
    r = math.radians(grados)
    c, s = math.cos(r), math.sin(r)
    return p * c + q * s, q * c - p * s


def deshacer(p: float, q: float, grados: float) -> tuple[float, float]:
    """Inversa de rotar: P = P'*cos a - Q'*sin a; Q = Q'*cos a + P'*sin a."""
    return rotar(p, q, -grados)


def _es_entero(x: float) -> bool:
    return abs(x - round(x)) <= TOLERANCIA


def _pasa_test(p: float, q: float, grados: float) -> bool:
    p_raw, q_raw = deshacer(p, q, grados)
    return _es_entero(p_raw) and _es_entero(q_raw)


def identificar(pr: float, qr: float, ps: float, qs: float) -> tuple[str | None, str]:
    """Devuelve (configuración, estado). Estado: ok, ambigua o no_identificable."""
    cumplen = [
        nombre
        for nombre, cfg in CONFIGURACIONES.items()
        if _pasa_test(pr, qr, cfg["R"]) and _pasa_test(ps, qs, cfg["S"])
    ]
    if len(cumplen) == 1:
        return cumplen[0], "ok"
    if cumplen:
        return None, "ambigua"
    return None, "no_identificable"


def _clamp(x: float) -> float:
    return max(-1.0, min(1.0, x))


def _redondear_fp(x: float | None) -> float | None:
    return None if x is None else round(x, 2)


def recalcular_fila(fila: Fila, configuracion: str) -> dict[str, float | None]:
    """Valores nuevos de las columnas de potencia para una fila con configuración conocida."""
    cfg = CONFIGURACIONES[configuracion]
    pr_raw, qr_raw = deshacer(float(fila["active_power_r"]), float(fila["reactive_power_r"]), cfg["R"])
    ps_raw, qs_raw = deshacer(float(fila["active_power_s"]), float(fila["reactive_power_s"]), cfg["S"])
    pr, qr = rotar(pr_raw, qr_raw, DESTINO["R"])
    ps, qs = rotar(ps_raw, qs_raw, DESTINO["S"])
    p_tot = pr + ps
    q_tot = qr + qs
    s_r = _opcional(fila["apparent_power_r"])
    s_s = _opcional(fila["apparent_power_s"])
    s_tot = _opcional(fila["total_apparent_power"])
    fp_r: float | None = _clamp(pr / s_r) if s_r is not None and s_r > 0 else _opcional(fila["power_factor_r"])
    fp_s: float | None = _clamp(ps / s_s) if s_s is not None and s_s > 0 else _opcional(fila["power_factor_s"])
    fp_tot: float | None = (
        _clamp(p_tot / s_tot) if s_tot is not None and s_tot > 0 else _opcional(fila["total_power_factor"])
    )
    return {
        "active_power_r": round(pr, 2),
        "reactive_power_r": round(qr, 2),
        "power_factor_r": _redondear_fp(fp_r),
        "active_power_s": round(ps, 2),
        "reactive_power_s": round(qs, 2),
        "power_factor_s": _redondear_fp(fp_s),
        "total_active_power": round(p_tot, 2),
        "total_reactive_power": round(q_tot, 2),
        "total_power_factor": _redondear_fp(fp_tot),
    }


def _opcional(valor: Any) -> float | None:
    return None if valor is None else float(valor)


# --- Lectura del respaldo ---------------------------------------------------------------

_TUPLA = re.compile(r"\(([^()]*)\)")


def leer_respaldo(ruta: Path) -> tuple[list[Fila], list[Fila]]:
    """Lee solo las líneas de telemetry_instantaneous y telemetry_energy. Ignora el resto."""
    columnas: dict[str, list[str]] = {}
    instant: list[Fila] = []
    energia: list[Fila] = []
    tabla_actual: str | None = None
    with ruta.open(encoding="utf-8") as f:
        for linea in f:
            if linea.startswith("CREATE TABLE `telemetry_instantaneous`"):
                tabla_actual = "telemetry_instantaneous"
                columnas[tabla_actual] = []
                continue
            if linea.startswith("CREATE TABLE `telemetry_energy`"):
                tabla_actual = "telemetry_energy"
                columnas[tabla_actual] = []
                continue
            if tabla_actual is not None and linea.startswith(") ENGINE"):
                tabla_actual = None
                continue
            if tabla_actual is not None and linea.startswith("  `"):
                columnas[tabla_actual].append(linea.split("`")[1])
                continue
            if linea.startswith("INSERT INTO `telemetry_instantaneous`"):
                instant.extend(_filas(linea, columnas["telemetry_instantaneous"], solo_acc=False))
            elif linea.startswith("INSERT INTO `telemetry_energy`"):
                energia.extend(_filas(linea, columnas["telemetry_energy"], solo_acc=True))
    return instant, energia


def _filas(linea: str, columnas: list[str], solo_acc: bool) -> list[Fila]:
    salida: list[Fila] = []
    cuerpo = linea.split("VALUES", 1)[1]
    for m in _TUPLA.finditer(cuerpo):
        valores = [v.strip().strip("'") for v in m.group(1).split(",")]
        if len(valores) != len(columnas):
            raise ValueError(f"fila con {len(valores)} valores, se esperaban {len(columnas)}")
        fila: Fila = {c: (None if v == "NULL" else v) for c, v in zip(columnas, valores, strict=True)}
        if fila["device_id"] != DISPOSITIVO_ID:
            continue
        if solo_acc and fila.get("source") != "acc":
            continue
        salida.append(fila)
    return salida


# --- Potencia instantánea ----------------------------------------------------------------


def procesar_instantanea(filas: list[Fila], desde: str, hasta: str | None) -> list[dict[str, Any]]:
    """Clasifica cada fila y calcula los valores nuevos cuando la configuración es conocida."""
    salida: list[dict[str, Any]] = []
    for fila in filas:
        marca = str(fila["recorded_at"])
        if marca < desde or (hasta is not None and marca >= hasta):
            continue
        if any(fila[c] is None for c in ("active_power_r", "reactive_power_r", "active_power_s", "reactive_power_s")):
            salida.append({"fila": fila, "estado": "sin_datos", "config": None, "nuevo": None})
            continue
        config, estado = identificar(
            float(fila["active_power_r"]),
            float(fila["reactive_power_r"]),
            float(fila["active_power_s"]),
            float(fila["reactive_power_s"]),
        )
        if estado != "ok":
            salida.append({"fila": fila, "estado": estado, "config": None, "nuevo": None})
        elif config == "R-60_S0":
            salida.append({"fila": fila, "estado": "ya_corregida", "config": config, "nuevo": None})
        else:
            salida.append(
                {"fila": fila, "estado": "aplicar", "config": config, "nuevo": recalcular_fila(fila, str(config))}
            )
    return salida


# --- Energía -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Muestra:
    t: datetime
    p_raw: float
    q_raw: float
    p_corr: float
    q_corr: float


def muestras_desde_filas(procesadas: list[dict[str, Any]]) -> list[Muestra]:
    """Muestras con P y Q crudas y corregidas. Las filas sin configuración determinable no entran."""
    salida: list[Muestra] = []
    for item in procesadas:
        if item["estado"] not in ("aplicar", "ya_corregida"):
            continue
        fila: Fila = item["fila"]
        config = str(item["config"]) if item["config"] else "R-60_S0"
        cfg = CONFIGURACIONES[config]
        pr_raw, qr_raw = deshacer(float(fila["active_power_r"]), float(fila["reactive_power_r"]), cfg["R"])
        ps_raw, qs_raw = deshacer(float(fila["active_power_s"]), float(fila["reactive_power_s"]), cfg["S"])
        nuevo = item["nuevo"] if item["nuevo"] is not None else recalcular_fila(fila, "R-60_S0")
        salida.append(
            Muestra(
                t=datetime.strptime(str(fila["recorded_at"]), FORMATO_FECHA),
                p_raw=pr_raw + ps_raw,
                q_raw=qr_raw + qs_raw,
                p_corr=float(nuevo["active_power_r"] or 0) + float(nuevo["active_power_s"] or 0),
                q_corr=float(nuevo["reactive_power_r"] or 0) + float(nuevo["reactive_power_s"] or 0),
            )
        )
    salida.sort(key=lambda m: m.t)
    return salida


def _horas(delta: timedelta) -> float:
    return delta.total_seconds() / 3600.0


class Acumulado:
    """Energía acumulada (kWh o kvarh) con ancla en el valor del medidor antes del tramo.

    Entre muestras, trapecio. Dentro de un intervalo, interpolación lineal del acumulado.
    Entre el ancla y la primera muestra, y después de la última, se mantiene el valor
    de la muestra más cercana.
    """

    def __init__(self, t_ancla: datetime, ancla: float, tiempos: list[datetime], valores: list[float]):
        if not tiempos:
            raise ValueError("sin muestras para acumular")
        self.t_ancla = t_ancla
        self.ancla = ancla
        self.tiempos = tiempos
        self.valores = valores
        self.pre = valores[0] * _horas(tiempos[0] - t_ancla) / 1000.0
        self.cum: list[float] = [0.0]
        for i in range(1, len(tiempos)):
            tramo = (valores[i - 1] + valores[i]) / 2.0 * _horas(tiempos[i] - tiempos[i - 1]) / 1000.0
            self.cum.append(self.cum[-1] + tramo)

    def en(self, t: datetime) -> float:
        if t <= self.tiempos[0]:
            return self.ancla + self.valores[0] * _horas(t - self.t_ancla) / 1000.0
        if t >= self.tiempos[-1]:
            return self.ancla + self.pre + self.cum[-1]
        i = bisect.bisect_right(self.tiempos, t) - 1
        frac = _horas(t - self.tiempos[i]) / _horas(self.tiempos[i + 1] - self.tiempos[i])
        return self.ancla + self.pre + self.cum[i] + (self.cum[i + 1] - self.cum[i]) * frac


def huecos(muestras: list[Muestra]) -> list[tuple[datetime, datetime, float]]:
    salida: list[tuple[datetime, datetime, float]] = []
    for a, b in itertools.pairwise(muestras):
        minutos = (b.t - a.t).total_seconds() / 60.0
        if minutos > HUECO_MIN:
            salida.append((a.t, b.t, round(minutos, 1)))
    return salida


def recalcular_energia(
    energia: list[Fila], muestras: list[Muestra], desde: str, hasta: str | None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Filas nuevas de telemetry_energy y validación con P cruda contra el medidor."""
    previas = [e for e in energia if str(e["recorded_at"]) < desde]
    if not previas:
        raise ValueError("no hay fila de energía anterior a desde: no hay ancla")
    ancla_fila = max(previas, key=lambda e: str(e["recorded_at"]))
    t_ancla = datetime.strptime(str(ancla_fila["recorded_at"]), FORMATO_FECHA)
    ancla_p = float(ancla_fila["net_active_energy_kwh"] or 0)
    ancla_q = float(ancla_fila["net_reactive_energy_kvarh"] or 0)

    objetivo = [
        e for e in energia if str(e["recorded_at"]) >= desde and (hasta is None or str(e["recorded_at"]) < hasta)
    ]
    objetivo.sort(key=lambda e: str(e["recorded_at"]))
    if not muestras:
        raise ValueError("sin muestras instantáneas en la ventana")

    tiempos = [m.t for m in muestras]
    acum_p = Acumulado(t_ancla, ancla_p, tiempos, [m.p_corr for m in muestras])
    acum_q = Acumulado(t_ancla, ancla_q, tiempos, [m.q_corr for m in muestras])
    acum_raw = Acumulado(t_ancla, 0.0, tiempos, [m.p_raw for m in muestras])
    lista_huecos = huecos(muestras)

    filas: list[dict[str, Any]] = []
    for e in objetivo:
        t = datetime.strptime(str(e["recorded_at"]), FORMATO_FECHA)
        neta_p = round(acum_p.en(t), 3)
        neta_q = round(acum_q.en(t), 3)
        en_hueco = any(a < t < b for a, b, _ in lista_huecos)
        filas.append(
            {
                "id": e["id"],
                "recorded_at": e["recorded_at"],
                "antes": {c: e[c] for c in COLUMNAS_ENERGIA},
                "despues": {
                    "net_active_energy_kwh": neta_p,
                    "imported_active_energy_kwh": neta_p,
                    "net_reactive_energy_kvarh": neta_q,
                    "imported_reactive_energy_kvarh": neta_q,
                },
                "marca": "en_hueco" if en_hueco else "ok",
            }
        )
    return filas, _validar_contra_medidor(objetivo, acum_raw)


def _validar_contra_medidor(objetivo: list[Fila], acum_raw: Acumulado) -> dict[str, Any]:
    """Cociente medidor / integral de P cruda: ventana completa y por día (|ΔE| ≥ 50 kWh)."""
    if len(objetivo) < 2:
        return {"ventana": None, "dias": []}
    tiempos = [datetime.strptime(str(e["recorded_at"]), FORMATO_FECHA) for e in objetivo]
    med = [float(e["net_active_energy_kwh"] or 0) for e in objetivo]
    d_med = med[-1] - med[0]
    d_raw = acum_raw.en(tiempos[-1]) - acum_raw.en(tiempos[0])
    ventana = {
        "dE_medidor": round(d_med, 2),
        "integral_cruda": round(d_raw, 2),
        "cociente": round(d_med / d_raw, 4) if d_raw else None,
    }
    ultimo_por_dia: dict[str, int] = {}
    for i, t in enumerate(tiempos):
        ultimo_por_dia[t.strftime("%Y-%m-%d")] = i
    dias: list[dict[str, Any]] = []
    previo = 0
    for dia in sorted(ultimo_por_dia):
        idx = ultimo_por_dia[dia]
        d_m = med[idx] - med[previo]
        d_r = acum_raw.en(tiempos[idx]) - acum_raw.en(tiempos[previo])
        if abs(d_m) >= 50.0:
            cociente = d_m / d_r if d_r else None
            dias.append(
                {
                    "dia_utc": dia,
                    "dE_medidor": round(d_m, 2),
                    "integral_cruda": round(d_r, 2),
                    "cociente": round(cociente, 4) if cociente is not None else None,
                    "fuera_5pct": cociente is None or abs(cociente - 1) > 0.05,
                }
            )
        previo = idx
    return {"ventana": ventana, "dias": dias}


# --- Estadística de control --------------------------------------------------------------


def _angulo(p: float, q: float) -> float:
    return math.degrees(math.atan2(q, p))


def control_post(procesadas: list[dict[str, Any]]) -> dict[str, Any]:
    """Ángulos del estado solo banco y fracción de P<0 en turno, con los valores nuevos."""
    banco_r: list[float] = []
    banco_s: list[float] = []
    turno_tot: list[bool] = []
    turno_r: list[bool] = []
    turno_s: list[bool] = []
    for item in procesadas:
        nuevo = item["nuevo"]
        if nuevo is None:
            continue
        pr, qr = float(nuevo["active_power_r"]), float(nuevo["reactive_power_r"])
        ps, qs = float(nuevo["active_power_s"]), float(nuevo["reactive_power_s"])
        t_utc = datetime.strptime(str(item["fila"]["recorded_at"]), FORMATO_FECHA).replace(tzinfo=timezone.utc)
        t_loc = t_utc.astimezone(UTC_LOCAL)
        if 1 <= t_loc.hour < 6 and abs(pr + ps) < 2000:
            banco_r.append(_angulo(pr, qr))
            banco_s.append(_angulo(ps, qs))
        if t_loc.weekday() < 5 and 6 <= t_loc.hour < 14:
            turno_tot.append(pr + ps < 0)
            turno_r.append(pr < 0)
            turno_s.append(ps < 0)
    return {
        "solo_banco_R_mediana_deg": _mediana(banco_r),
        "solo_banco_S_mediana_deg": _mediana(banco_s),
        "solo_banco_n": len(banco_r),
        "turno_fraccion_P_total_negativa": _fraccion(turno_tot),
        "turno_fraccion_P_R_negativa": _fraccion(turno_r),
        "turno_fraccion_P_S_negativa": _fraccion(turno_s),
        "turno_n": len(turno_tot),
    }


def _mediana(valores: list[float]) -> float | None:
    if not valores:
        return None
    s = sorted(valores)
    n = len(s)
    return round(s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2, 2)


def _fraccion(valores: list[bool]) -> float | None:
    return round(sum(valores) / len(valores), 4) if valores else None


# --- SQL ---------------------------------------------------------------------------------


def _literal(valor: Any, decimales: int) -> str:
    """Literal numérico SQL. El valor viene del respaldo (string) o de un float."""
    if valor is None:
        return "NULL"
    if isinstance(valor, str):
        return valor
    return f"{valor:.{decimales}f}"


def _guarda(columna: str, valor: Any, decimales: int) -> str:
    return f"{columna} <=> {_literal(valor, decimales)}"


def sql_instantanea(filas: list[dict[str, Any]], revertir: bool) -> str:
    lineas: list[str] = []
    for item in filas:
        fila: Fila = item["fila"]
        nuevo: dict[str, float | None] = item["nuevo"]
        origen: dict[str, Any] = nuevo if revertir else fila
        destino: dict[str, Any] = fila if revertir else nuevo
        sets = [f"{c} = {_literal(_texto(destino[c]), 2)}" for c in COLUMNAS_POTENCIA]
        guardas = [_guarda(c, _texto(origen[c]), 2) for c in COLUMNAS_POTENCIA]
        lineas.append(
            f"UPDATE telemetry_instantaneous SET {', '.join(sets)} WHERE id = {fila['id']} AND {' AND '.join(guardas)};"
        )
    return "\n".join(lineas) + "\n"


def sql_energia(filas: list[dict[str, Any]], revertir: bool) -> str:
    lineas: list[str] = []
    for item in filas:
        origen: dict[str, Any] = item["despues"] if revertir else item["antes"]
        destino: dict[str, Any] = item["antes"] if revertir else item["despues"]
        sets = [f"{c} = {_literal(_texto(destino[c]), 3)}" for c in COLUMNAS_ENERGIA]
        guardas = [_guarda(c, _texto(origen[c]), 3) for c in COLUMNAS_ENERGIA]
        lineas.append(
            f"UPDATE telemetry_energy SET {', '.join(sets)} WHERE id = {item['id']} AND {' AND '.join(guardas)};"
        )
    return "\n".join(lineas) + "\n"


def _texto(valor: Any) -> str | None:
    """Pasa a texto un valor de fila o de cálculo, sin redondear de más."""
    if valor is None:
        return None
    if isinstance(valor, float):
        return f"{valor:.6f}"
    return str(valor)


def envolver_transaccion(cuerpo: str, encabezado: str, esperadas: int) -> str:
    return (
        f"-- {encabezado}\n"
        f"-- Filas esperadas: {esperadas}. Cada UPDATE debe afectar 1 fila (ROW_COUNT() = 1).\n"
        "-- Si alguno afecta 0 filas, hacer ROLLBACK y no seguir.\n"
        "START TRANSACTION;\n"
        f"{cuerpo}"
        "COMMIT;\n"
    )


# --- Salidas -----------------------------------------------------------------------------


def escribir_plan_instantanea(ruta: Path, filas: list[dict[str, Any]]) -> None:
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        cabecera = ["id", "recorded_at", "estado", "config_antes"]
        for c in COLUMNAS_POTENCIA:
            cabecera += [f"{c}_antes", f"{c}_despues"]
        w.writerow(cabecera)
        for item in filas:
            fila: Fila = item["fila"]
            nuevo = item["nuevo"]
            registro: list[Any] = [fila["id"], fila["recorded_at"], item["estado"], item["config"] or ""]
            for c in COLUMNAS_POTENCIA:
                registro += [fila[c], nuevo[c] if nuevo is not None else ""]
            w.writerow(registro)


def escribir_plan_energia(ruta: Path, filas: list[dict[str, Any]]) -> None:
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        cabecera = ["id", "recorded_at", "marca"]
        for c in COLUMNAS_ENERGIA:
            cabecera += [f"{c}_antes", f"{c}_despues"]
        w.writerow(cabecera)
        for item in filas:
            registro: list[Any] = [item["id"], item["recorded_at"], item["marca"]]
            for c in COLUMNAS_ENERGIA:
                registro += [item["antes"][c], item["despues"][c]]
            w.writerow(registro)


def _formatear_resumen(resumen: dict[str, Any]) -> str:
    lineas = [f"{k}: {v}" for k, v in resumen.items() if k != "huecos_mayores_15min"]
    lineas.append("huecos_mayores_15min:")
    for a, b, m in resumen["huecos_mayores_15min"]:
        lineas.append(f"  {a} -> {b}: {m} min")
    return "\n".join(lineas) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--respaldo", type=Path, default=RESPALDO_DEFAULT)
    parser.add_argument("--desde", default=DESDE_DEFAULT, help="Fecha UTC inclusive, AAAA-MM-DD HH:MM:SS")
    parser.add_argument("--hasta", default=None, help="Fecha UTC exclusiva, AAAA-MM-DD HH:MM:SS")
    parser.add_argument("--salida", type=Path, default=SALIDA_DEFAULT)
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument("--en-seco", action="store_true", help="Solo plan, sin SQL")
    modo.add_argument("--generar-sql", action="store_true", help="Plan y SQL de aplicación y reversión")
    args = parser.parse_args(argv)

    args.salida.mkdir(parents=True, exist_ok=True)
    instant, energia = leer_respaldo(args.respaldo)
    procesadas = procesar_instantanea(instant, args.desde, args.hasta)
    conteo: dict[str, int] = {}
    for item in procesadas:
        conteo[str(item["estado"])] = conteo.get(str(item["estado"]), 0) + 1
    aplicar = [i for i in procesadas if i["estado"] == "aplicar"]

    muestras = muestras_desde_filas(procesadas)
    filas_energia, validacion = recalcular_energia(energia, muestras, args.desde, args.hasta)
    resumen: dict[str, Any] = {
        "instantaneas_en_ventana": len(procesadas),
        "estados": conteo,
        "energia_filas": len(filas_energia),
        "energia_en_hueco": sum(1 for f in filas_energia if f["marca"] == "en_hueco"),
        "huecos_mayores_15min": [(str(a), str(b), m) for a, b, m in huecos(muestras)],
        "validacion_energia": validacion,
        "control_post": control_post(procesadas),
    }
    escribir_plan_instantanea(args.salida / "plan_instantanea.csv", procesadas)
    escribir_plan_energia(args.salida / "plan_energia.csv", filas_energia)
    (args.salida / "resumen.txt").write_text(_formatear_resumen(resumen), encoding="utf-8")

    if args.generar_sql:
        escritos = {
            "aplicar_instantanea.sql": envolver_transaccion(
                sql_instantanea(aplicar, revertir=False),
                "Recalculo potencia instantanea Trafo 2 (medidor 369) a R:-60,S:0 (#92, D2)",
                len(aplicar),
            ),
            "revertir_instantanea.sql": envolver_transaccion(
                sql_instantanea(aplicar, revertir=True),
                "Reversion del recalculo de potencia instantanea (valores originales)",
                len(aplicar),
            ),
            "aplicar_energia.sql": envolver_transaccion(
                sql_energia(filas_energia, revertir=False),
                "Recalculo energia Trafo 2 (medidor 369) desde potencia corregida (#92, D3)",
                len(filas_energia),
            ),
            "revertir_energia.sql": envolver_transaccion(
                sql_energia(filas_energia, revertir=True),
                "Reversion del recalculo de energia (valores originales)",
                len(filas_energia),
            ),
        }
        for nombre, contenido in escritos.items():
            (args.salida / nombre).write_text(contenido, encoding="utf-8")

    print(_formatear_resumen(resumen))
    print(f"Salida: {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Recalcula el Trafo 2 de San Martín (medidor 369) con la corrección R:-60,S:0.

Decisión: decisions/2026-10-29_correccion-angular-trafo2-banco-fijo.md (D2 potencia
instantánea y D3 energía). Issue: datamaq-automation/datamaq#92.

Potencia instantánea. El medidor reporta P y Q enteros. Por eso el ángulo aplicado a cada
fila se identifica deshaciendo cada configuración conocida y comprobando que el resultado
sea entero (tolerancia 0,02). El signo de R no lo da el test (0° y 180° dan enteros), así
que la configuración se decide con R y S juntos. Con el crudo recuperado se rota con
R:-60,S:0 y se recalculan P, Q, FP y totales. V, I y la aparente por fase no cambian.

Energía (telemetry_energy, source='acc'). Se ancla AL FINAL: el valor de cada fila es
medidor(T) - ∫ corregida (fila → T), donde T es la última fila de la entrada. Así la
última fila no cambia y la serie empalma con la siguiente lectura del medidor. Las filas
anteriores al inicio del recálculo (17/09 a 25/09) conservan sus diferencias medidas y se
desplazan una constante, c = E(primera fila integrada) - medidor(primera fila integrada),
para empalmar sin salto con la primera fila integrada.

Controles de energía: para cada par de filas integradas consecutivas se compara
Δ de la serie con la integral trapezoidal independiente del intervalo (con la P corregida
interpolada en los bordes). Se reporta el máximo |Δ - ∫|, y cuántos pares superan un
margen de 0,5 kWh.

Entrada: el respaldo .sql (solo INSERT de telemetry_instantaneous y telemetry_energy), o
dos CSV/TSV exportados de producción con exportar_trafo2.sql (solo lectura).

Nunca se conecta a una base. El SQL lo ejecuta DevOps.

Uso:
  python3 scripts/recalcular_trafo2_banco.py --en-seco
  python3 scripts/recalcular_trafo2_banco.py --generar-sql --instantanea-csv I.tsv --energia-csv E.tsv
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
DESDE_ENERGIA_DEFAULT = "2026-09-17 00:00:00"
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
MARGEN_SALTO_KWH = 0.5
REINICIO_UTC = "2026-10-30 00:10:45"
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
    """Misma convención que rotar_fase_fasorial: P' = P*cos a + Q*sin a; Q' = Q*cos a - P*sin a."""
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


def _opcional(valor: Any) -> float | None:
    return None if valor is None else float(valor)


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


# --- Lectura: respaldo .sql o CSV/TSV exportados -----------------------------------------

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
                instant.extend(_filas(linea, columnas["telemetry_instantaneous"]))
            elif linea.startswith("INSERT INTO `telemetry_energy`"):
                energia.extend(_filas(linea, columnas["telemetry_energy"]))
    return instant, energia


def _filas(linea: str, columnas: list[str]) -> list[Fila]:
    salida: list[Fila] = []
    cuerpo = linea.split("VALUES", 1)[1]
    for m in _TUPLA.finditer(cuerpo):
        valores = [v.strip().strip("'") for v in m.group(1).split(",")]
        if len(valores) != len(columnas):
            raise ValueError(f"fila con {len(valores)} valores, se esperaban {len(columnas)}")
        fila: Fila = {c: (None if v == "NULL" else v) for c, v in zip(columnas, valores, strict=True)}
        if fila["device_id"] == DISPOSITIVO_ID:
            salida.append(fila)
    return salida


def leer_tabla_exportada(ruta: Path) -> list[Fila]:
    """CSV o TSV (salida de mysql --batch). Separador detectado por la cabecera."""
    with ruta.open(encoding="utf-8", newline="") as f:
        cabecera = f.readline()
        separador = "\t" if "\t" in cabecera else ","
        f.seek(0)
        lector = csv.DictReader(f, delimiter=separador)
        filas: list[Fila] = []
        for registro in lector:
            fila: Fila = {k: (None if v in (None, "", "NULL") else v) for k, v in registro.items()}
            if fila.get("device_id") == DISPOSITIVO_ID:
                filas.append(fila)
    return filas


# --- Potencia instantánea ----------------------------------------------------------------


def procesar_instantanea(filas: list[Fila], desde: str) -> list[dict[str, Any]]:
    """Clasifica cada fila desde `desde` y calcula los valores nuevos cuando la configuración es conocida."""
    salida: list[dict[str, Any]] = []
    for fila in filas:
        if str(fila["recorded_at"]) < desde:
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


def filtrar_hasta(items: list[dict[str, Any]], hasta: str | None) -> list[dict[str, Any]]:
    if hasta is None:
        return items
    return [i for i in items if str(i["fila"]["recorded_at"]) < hasta]


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
        t = datetime.strptime(str(fila["recorded_at"]), FORMATO_FECHA)
        if item["estado"] == "ya_corregida":
            # Ya está en R:-60,S:0 en producción: se integra el valor almacenado, sin volver a rotar.
            p_corr = float(fila["active_power_r"]) + float(fila["active_power_s"])
            q_corr = float(fila["reactive_power_r"]) + float(fila["reactive_power_s"])
            pr_raw, qr_raw = deshacer(float(fila["active_power_r"]), float(fila["reactive_power_r"]), DESTINO["R"])
            ps_raw, qs_raw = deshacer(float(fila["active_power_s"]), float(fila["reactive_power_s"]), DESTINO["S"])
        else:
            nuevo = item["nuevo"]
            cfg = CONFIGURACIONES[str(item["config"])]
            pr_raw, qr_raw = deshacer(float(fila["active_power_r"]), float(fila["reactive_power_r"]), cfg["R"])
            ps_raw, qs_raw = deshacer(float(fila["active_power_s"]), float(fila["reactive_power_s"]), cfg["S"])
            p_corr = float(nuevo["active_power_r"] or 0) + float(nuevo["active_power_s"] or 0)
            q_corr = float(nuevo["reactive_power_r"] or 0) + float(nuevo["reactive_power_s"] or 0)
        salida.append(
            Muestra(
                t=t,
                p_raw=pr_raw + ps_raw,
                q_raw=qr_raw + qs_raw,
                p_corr=p_corr,
                q_corr=q_corr,
            )
        )
    salida.sort(key=lambda m: m.t)
    return salida


def _horas(delta: timedelta) -> float:
    return delta.total_seconds() / 3600.0


class Acumulado:
    """Acumulado (kWh o kvarh) de una serie de muestras, con origen en la primera muestra.

    Entre muestras, trapecio. Dentro de un intervalo, interpolación lineal del acumulado.
    Antes de la primera muestra se extiende hacia atrás con el valor de la primera muestra;
    después de la última, se mantiene el acumulado de la última.
    """

    def __init__(self, tiempos: list[datetime], valores: list[float]):
        if len(tiempos) < 2:
            raise ValueError("se necesitan al menos dos muestras para acumular")
        self.tiempos = tiempos
        self.valores = valores
        self.cum: list[float] = [0.0]
        for i in range(1, len(tiempos)):
            tramo = (valores[i - 1] + valores[i]) / 2.0 * _horas(tiempos[i] - tiempos[i - 1]) / 1000.0
            self.cum.append(self.cum[-1] + tramo)

    def en(self, t: datetime) -> float:
        if t <= self.tiempos[0]:
            return -self.valores[0] * _horas(self.tiempos[0] - t) / 1000.0
        if t >= self.tiempos[-1]:
            return self.cum[-1]
        i = bisect.bisect_right(self.tiempos, t) - 1
        frac = _horas(t - self.tiempos[i]) / _horas(self.tiempos[i + 1] - self.tiempos[i])
        return self.cum[i] + (self.cum[i + 1] - self.cum[i]) * frac

    def valor_en(self, t: datetime) -> float:
        """Valor de la serie (potencia) interpolado linealmente en t."""
        if t <= self.tiempos[0]:
            return self.valores[0]
        if t >= self.tiempos[-1]:
            return self.valores[-1]
        i = bisect.bisect_right(self.tiempos, t) - 1
        frac = _horas(t - self.tiempos[i]) / _horas(self.tiempos[i + 1] - self.tiempos[i])
        return self.valores[i] + (self.valores[i + 1] - self.valores[i]) * frac


def huecos(muestras: list[Muestra]) -> list[tuple[datetime, datetime, float]]:
    salida: list[tuple[datetime, datetime, float]] = []
    for a, b in itertools.pairwise(muestras):
        minutos = (b.t - a.t).total_seconds() / 60.0
        if minutos > HUECO_MIN:
            salida.append((a.t, b.t, round(minutos, 1)))
    return salida


def _integral_independiente(
    muestras_t: list[datetime], muestras_v: list[float], ta: datetime, tb: datetime, serie: Acumulado
) -> float:
    """Trapecio en [ta, tb] con los bordes interpolados y las muestras intermedias (kWh)."""
    puntos: list[tuple[datetime, float]] = [(ta, serie.valor_en(ta))]
    puntos += [(t, v) for t, v in zip(muestras_t, muestras_v, strict=True) if ta < t < tb]
    puntos.append((tb, serie.valor_en(tb)))
    return sum((pa[1] + pb[1]) / 2.0 * _horas(pb[0] - pa[0]) / 1000.0 for pa, pb in itertools.pairwise(puntos))


def recalcular_energia(
    energia: list[Fila],
    muestras: list[Muestra],
    desde: str,
    desde_energia: str,
    ambiguas: list[datetime] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Filas nuevas de telemetry_energy (anclaje al final) y controles de la serie."""
    if not muestras:
        raise ValueError("sin muestras instantáneas en la ventana")
    filas = sorted(
        (e for e in energia if str(e["recorded_at"]) >= desde_energia),
        key=lambda e: str(e["recorded_at"]),
    )
    if not filas:
        raise ValueError("sin filas de energía desde desde_energia")
    fila_t = filas[-1]
    t_final = datetime.strptime(str(fila_t["recorded_at"]), FORMATO_FECHA)
    m_final_p = float(fila_t["net_active_energy_kwh"] or 0)
    m_final_q = float(fila_t["net_reactive_energy_kvarh"] or 0)

    tiempos = [m.t for m in muestras]
    acum_p = Acumulado(tiempos, [m.p_corr for m in muestras])
    acum_q = Acumulado(tiempos, [m.q_corr for m in muestras])
    acum_raw = Acumulado(tiempos, [m.p_raw for m in muestras])
    cum_p_final = acum_p.en(t_final)
    cum_q_final = acum_q.en(t_final)
    lista_huecos = huecos(muestras)

    def e_p(t: datetime) -> float:
        return m_final_p + acum_p.en(t) - cum_p_final

    def e_q(t: datetime) -> float:
        return m_final_q + acum_q.en(t) - cum_q_final

    t_desde = datetime.strptime(desde, FORMATO_FECHA)
    integradas = [e for e in filas if str(e["recorded_at"]) >= desde]
    primera_integrada = integradas[0]
    t_primera = datetime.strptime(str(primera_integrada["recorded_at"]), FORMATO_FECHA)
    c_p = e_p(t_primera) - float(primera_integrada["net_active_energy_kwh"] or 0)
    c_q = e_q(t_primera) - float(primera_integrada["net_reactive_energy_kvarh"] or 0)

    tiempos = sorted(tiempos)
    ambiguas_ord = sorted(ambiguas or [])
    filas_salida: list[dict[str, Any]] = []
    for e in filas:
        t = datetime.strptime(str(e["recorded_at"]), FORMATO_FECHA)
        medido_p = float(e["net_active_energy_kwh"] or 0)
        medido_q = float(e["net_reactive_energy_kvarh"] or 0)
        if t < t_desde:
            nueva_p = medido_p + c_p
            nueva_q = medido_q + c_q
            marca = "pre_desplazada"
        else:
            nueva_p = e_p(t)
            nueva_q = e_q(t)
            i_prev = bisect.bisect_right(tiempos, t) - 1
            i_next = i_prev + 1
            cruza_ambigua = (
                i_next < len(tiempos)
                and i_prev >= 0
                and tiempos[i_prev] < t < tiempos[i_next]
                and any(tiempos[i_prev] < a < tiempos[i_next] for a in ambiguas_ord)
            )
            if any(a < t < b for a, b, _ in lista_huecos):
                marca = "en_hueco"
            elif cruza_ambigua:
                marca = "interpolada_ambigua"
            else:
                marca = "integrada"
        nueva_p = round(nueva_p, 3)
        nueva_q = round(nueva_q, 3)
        antes = {c: e[c] for c in COLUMNAS_ENERGIA}
        despues = {
            "net_active_energy_kwh": nueva_p,
            "imported_active_energy_kwh": nueva_p,
            "net_reactive_energy_kvarh": nueva_q,
            "imported_reactive_energy_kvarh": nueva_q,
        }
        filas_salida.append(
            {
                "id": e["id"],
                "recorded_at": e["recorded_at"],
                "antes": antes,
                "despues": despues,
                "marca": marca,
                "cambia": any(abs(float(antes[c] or 0) - despues[c]) > 0.0005 for c in COLUMNAS_ENERGIA),
            }
        )

    controles = _controles(integradas, muestras, e_p, acum_p, acum_raw, filas, c_p, t_desde)
    controles["c_desplazamiento_pre"] = round(c_p, 3)
    controles["fila_final"] = {
        "recorded_at": str(fila_t["recorded_at"]),
        "medido_kwh": m_final_p,
        "recalculado_kwh": round(e_p(t_final), 3),
    }
    return filas_salida, controles


def _controles(
    integradas: list[Fila],
    muestras: list[Muestra],
    e_p: Any,
    acum_p: Acumulado,
    acum_raw: Acumulado,
    filas: list[Fila],
    c_p: float,
    t_desde: datetime,
) -> dict[str, Any]:
    """Validación con P cruda contra el medidor, y control de saltos de la serie resultante."""
    tiempos_int = [datetime.strptime(str(e["recorded_at"]), FORMATO_FECHA) for e in integradas]
    med = [float(e["net_active_energy_kwh"] or 0) for e in integradas]

    ventana: dict[str, Any] = {}
    if len(integradas) >= 2:
        d_med = med[-1] - med[0]
        d_raw = acum_raw.en(tiempos_int[-1]) - acum_raw.en(tiempos_int[0])
        ventana = {
            "dE_medidor": round(d_med, 2),
            "integral_cruda": round(d_raw, 2),
            "cociente": round(d_med / d_raw, 4) if d_raw else None,
        }

    ultimo_por_dia: dict[str, int] = {}
    for i, t in enumerate(tiempos_int):
        ultimo_por_dia[t.strftime("%Y-%m-%d")] = i
    dias: list[dict[str, Any]] = []
    previo = 0
    for dia in sorted(ultimo_por_dia):
        idx = ultimo_por_dia[dia]
        d_m = med[idx] - med[previo]
        d_r = acum_raw.en(tiempos_int[idx]) - acum_raw.en(tiempos_int[previo])
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

    # Saltos: Δ de la serie entre filas integradas consecutivas vs. integral independiente.
    m_muestras_t = [m.t for m in muestras]
    m_muestras_v = [m.p_corr for m in muestras]
    max_dif = 0.0
    max_dif_en = ""
    superan = 0
    for a, b in itertools.pairwise(range(len(integradas))):
        ta, tb = tiempos_int[a], tiempos_int[b]
        delta_serie = e_p(tb) - e_p(ta)
        integral = _integral_independiente(m_muestras_t, m_muestras_v, ta, tb, acum_p)
        dif = abs(delta_serie - integral / 1.0)
        if dif > max_dif:
            max_dif = dif
            max_dif_en = f"{integradas[a]['recorded_at']} -> {integradas[b]['recorded_at']}"
        if dif > MARGEN_SALTO_KWH:
            superan += 1

    # Empalme: entre la última fila desplazada y la primera integrada.
    previas = [
        e
        for e in filas
        if str(e["recorded_at"]) < str(integradas[0]["recorded_at"])
        and datetime.strptime(str(e["recorded_at"]), FORMATO_FECHA) < t_desde
    ]
    empalme: dict[str, Any] = {}
    if previas:
        ult = previas[-1]
        salto = (float(integradas[0]["net_active_energy_kwh"] or 0) + c_p) - (
            float(ult["net_active_energy_kwh"] or 0) + c_p
        )
        empalme = {
            "ultima_pre": str(ult["recorded_at"]),
            "primera_integrada": str(integradas[0]["recorded_at"]),
            "salto_kwh": round(salto, 3),
        }

    return {
        "validacion_ventana": ventana,
        "validacion_dias": dias,
        "max_abs_dif_delta_vs_integral_kwh": round(max_dif, 4),
        "max_abs_dif_en": max_dif_en,
        "pares_sobre_margen": superan,
        "margen_kwh": MARGEN_SALTO_KWH,
        "empalme": empalme,
    }


# --- Estadística de control --------------------------------------------------------------

UTC_LOCAL_HORA = UTC_LOCAL


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
        t_loc = t_utc.astimezone(UTC_LOCAL_HORA)
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


def _literal(valor: Any) -> str:
    """Literal numérico SQL a partir del texto del respaldo o de un float."""
    if valor is None:
        return "NULL"
    if isinstance(valor, str):
        return valor
    return f"{valor:.6f}"


def _guarda(columna: str, valor: Any) -> str:
    return f"{columna} <=> {_literal(valor)}"


def _device_guarda() -> str:
    return f"device_id = '{DISPOSITIVO_ID}'"


def sql_instantanea(filas: list[dict[str, Any]], revertir: bool) -> str:
    lineas: list[str] = []
    for item in filas:
        fila: Fila = item["fila"]
        nuevo: dict[str, float | None] = item["nuevo"]
        origen: dict[str, Any] = nuevo if revertir else fila
        destino: dict[str, Any] = fila if revertir else nuevo
        sets = [f"{c} = {_literal(destino[c])}" for c in COLUMNAS_POTENCIA]
        guardas = [_guarda(c, origen[c]) for c in COLUMNAS_POTENCIA]
        lineas.append(
            f"UPDATE telemetry_instantaneous SET {', '.join(sets)} "
            f"WHERE id = {fila['id']} AND {_device_guarda()} AND {' AND '.join(guardas)};"
        )
    return "\n".join(lineas) + "\n"


def sql_energia(filas: list[dict[str, Any]], revertir: bool) -> str:
    lineas: list[str] = []
    for item in filas:
        origen: dict[str, Any] = item["despues"] if revertir else item["antes"]
        destino: dict[str, Any] = item["antes"] if revertir else item["despues"]
        sets = [f"{c} = {_literal(destino[c])}" for c in COLUMNAS_ENERGIA]
        guardas = [_guarda(c, origen[c]) for c in COLUMNAS_ENERGIA]
        lineas.append(
            f"UPDATE telemetry_energy SET {', '.join(sets)} "
            f"WHERE id = {item['id']} AND {_device_guarda()} AND {' AND '.join(guardas)};"
        )
    return "\n".join(lineas) + "\n"


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
        cabecera = ["id", "recorded_at", "marca", "cambia"]
        for c in COLUMNAS_ENERGIA:
            cabecera += [f"{c}_antes", f"{c}_despues"]
        w.writerow(cabecera)
        for item in filas:
            registro: list[Any] = [item["id"], item["recorded_at"], item["marca"], item["cambia"]]
            for c in COLUMNAS_ENERGIA:
                registro += [item["antes"][c], item["despues"][c]]
            w.writerow(registro)


def _ejemplos(procesadas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aplicar = [i for i in procesadas if i["estado"] == "aplicar"]
    if not aplicar:
        return []
    indices = sorted({0, len(aplicar) // 4, len(aplicar) // 2, (3 * len(aplicar)) // 4, len(aplicar) - 1})
    return [aplicar[i] for i in indices][:5]


def _formatear_resumen(resumen: dict[str, Any]) -> str:
    lineas = [
        f"{k}: {v}"
        for k, v in resumen.items()
        if k not in ("huecos_mayores_15min", "control_energia", "control_post", "ejemplos")
    ]
    lineas.append("control_energia:")
    for k, v in resumen["control_energia"].items():
        if k != "validacion_dias":
            lineas.append(f"  {k}: {v}")
    lineas.append("dias_fuera_5pct_energia:")
    for d in resumen["control_energia"]["validacion_dias"]:
        if d["fuera_5pct"]:
            lineas.append(f"  {d}")
    lineas.append("control_post:")
    for k, v in resumen["control_post"].items():
        lineas.append(f"  {k}: {v}")
    lineas.append("huecos_mayores_15min:")
    for a, b, m in resumen["huecos_mayores_15min"]:
        lineas.append(f"  {a} -> {b}: {m} min")
    lineas.append("ejemplos_instantanea:")
    for ej in resumen["ejemplos"]:
        lineas.append(f"  {ej}")
    return "\n".join(lineas) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    fuente = parser.add_argument_group("entrada (una de las dos)")
    fuente.add_argument("--respaldo", type=Path, default=None, help="Respaldo .sql (por defecto el del 29/10)")
    fuente.add_argument("--instantanea-csv", type=Path, default=None, help="Export de telemetry_instantaneous")
    fuente.add_argument("--energia-csv", type=Path, default=None, help="Export de telemetry_energy")
    parser.add_argument("--desde", default=DESDE_DEFAULT, help="Inicio del recálculo UTC, AAAA-MM-DD HH:MM:SS")
    parser.add_argument("--desde-energia", default=DESDE_ENERGIA_DEFAULT, help="Primera fila de energía a tocar")
    parser.add_argument("--hasta", default=None, help="Solo se generan SQL para filas anteriores a esta fecha UTC")
    parser.add_argument("--salida", type=Path, default=SALIDA_DEFAULT)
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument("--en-seco", action="store_true", help="Solo plan, sin SQL")
    modo.add_argument("--generar-sql", action="store_true", help="Plan y SQL de aplicación y reversión")
    args = parser.parse_args(argv)

    if args.respaldo is not None and (args.instantanea_csv or args.energia_csv):
        parser.error("usar --respaldo o los CSV, no ambos")
    args.salida.mkdir(parents=True, exist_ok=True)
    if args.instantanea_csv or args.energia_csv:
        if not (args.instantanea_csv and args.energia_csv):
            parser.error("con CSV hay que dar --instantanea-csv y --energia-csv")
        instant = leer_tabla_exportada(args.instantanea_csv)
        energia = leer_tabla_exportada(args.energia_csv)
        origen = f"{args.instantanea_csv} + {args.energia_csv}"
    else:
        ruta = args.respaldo or RESPALDO_DEFAULT
        instant, energia = leer_respaldo(ruta)
        origen = str(ruta)
    energia = [e for e in energia if e.get("source", "acc") == "acc"]

    procesadas = procesar_instantanea(instant, args.desde)
    aplicar_todas = [i for i in procesadas if i["estado"] == "aplicar"]
    aplicar = filtrar_hasta(aplicar_todas, args.hasta)
    conteo: dict[str, int] = {}
    for item in procesadas:
        conteo[str(item["estado"])] = conteo.get(str(item["estado"]), 0) + 1

    muestras = muestras_desde_filas(procesadas)
    ambiguas = [
        datetime.strptime(str(i["fila"]["recorded_at"]), FORMATO_FECHA) for i in procesadas if i["estado"] == "ambigua"
    ]
    filas_energia, controles = recalcular_energia(energia, muestras, args.desde, args.desde_energia, ambiguas=ambiguas)
    filas_energia_sql = [f for f in filas_energia if f["cambia"]]
    if args.hasta is not None:
        filas_energia_sql = [f for f in filas_energia_sql if str(f["recorded_at"]) < args.hasta]

    resumen: dict[str, Any] = {
        "origen": origen,
        "ancla": "final (ultima fila de la entrada)",
        "instantaneas_desde": len(procesadas),
        "estados": conteo,
        "instantanea_a_actualizar": len(aplicar),
        "energia_filas_en_serie": len(filas_energia),
        "energia_filas_a_actualizar": len(filas_energia_sql),
        "energia_filas_pre_desplazadas": sum(1 for f in filas_energia if f["marca"] == "pre_desplazada"),
        "energia_en_hueco": sum(1 for f in filas_energia if f["marca"] == "en_hueco"),
        "energia_interpoladas_por_ambigua": sum(1 for f in filas_energia if f["marca"] == "interpolada_ambigua"),
        "energia_filas_posteriores_reinicio": sum(1 for f in filas_energia if str(f["recorded_at"]) >= REINICIO_UTC),
        "huecos_mayores_15min": [(str(a), str(b), m) for a, b, m in huecos(muestras)],
        "control_energia": controles,
        "control_post": control_post(procesadas),
        "ejemplos": [
            {
                "id": e["fila"]["id"],
                "recorded_at": e["fila"]["recorded_at"],
                "P_R": f"{e['fila']['active_power_r']} -> {e['nuevo']['active_power_r']}",
                "P_S": f"{e['fila']['active_power_s']} -> {e['nuevo']['active_power_s']}",
                "P_total": f"{e['fila']['total_active_power']} -> {e['nuevo']['total_active_power']}",
                "FP_R": f"{e['fila']['power_factor_r']} -> {e['nuevo']['power_factor_r']}",
            }
            for e in _ejemplos(aplicar)
        ],
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
                sql_energia(filas_energia_sql, revertir=False),
                "Recalculo energia Trafo 2 (medidor 369) anclado al final (#92, D3)",
                len(filas_energia_sql),
            ),
            "revertir_energia.sql": envolver_transaccion(
                sql_energia(filas_energia_sql, revertir=True),
                "Reversion del recalculo de energia (valores originales)",
                len(filas_energia_sql),
            ),
        }
        for nombre, contenido in escritos.items():
            (args.salida / nombre).write_text(contenido, encoding="utf-8")

    print(_formatear_resumen(resumen))
    print(f"Salida: {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

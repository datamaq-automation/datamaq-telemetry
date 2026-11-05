#!/usr/bin/env python3
"""Análisis por fase de un CSV de mediciones, para diagnosticar TI invertido o fases mal ordenadas.

Entrada (una fila por fase y por instante):
    timestamp,fase,V,I,P[,Q]
    2026-10-29T10:00:00Z,R,230.0,10.0,2000.0,1000.0

Por fase reporta: potencia activa media, fracción de tiempo con P negativa (con I >= umbral) y ángulo V-I
(atan2 de sumas de Q y P; sin Q solo hay magnitud). Si hay Q en las tres fases, reutiliza el ranking de
`DiagnosticoTIService.rankear_candidatos` (orden de fases x polaridad global).

Solo lectura: no toca la base ni la configuración. Pensado para un CSV exportado por DevOps.

Uso:
    .venv/bin/python scripts/analizar_fases_ti_csv.py --csv mediciones.csv --fases R,S,T
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

from src.domain.telemetria.servicios.diagnostico_ti import DiagnosticoTIService

UMBRAL_CORRIENTE_A = 2.0
"""Guarda de corriente: por debajo, la fase está en vacío y el signo de P es ruido (ver docs/deteccion-anomalias-fases-y-polaridad.md)."""

UMBRAL_FRACCION_P_NEGATIVA = 0.5
"""Si P es negativa más de esta fracción del tiempo, la fase es sospechosa de TI invertido."""


Medicion = dict[str, float]
"""Una fase en un instante: V, I, P y Q. Q es NaN si el CSV no la trae."""


def leer_mediciones(ruta: Path) -> dict[str, dict[str, Medicion]]:
    """Agrupa las filas por instante y fase: {timestamp: {fase: {V, I, P, Q}}}."""
    filas: dict[str, dict[str, Medicion]] = defaultdict(dict)
    with ruta.open(newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            q = fila.get("Q") or ""
            filas[fila["timestamp"]][fila["fase"].strip().upper()] = {
                "V": float(fila["V"]),
                "I": float(fila["I"]),
                "P": float(fila["P"]),
                "Q": float(q) if q.strip() else math.nan,
            }
    return dict(filas)


def estadisticas_por_fase(mediciones: dict[str, dict[str, Medicion]], fases: list[str]) -> dict[str, dict]:
    """Por fase: n, P media, fracción de P negativa, ángulo V-I (grados) y veredicto."""
    resultado: dict[str, dict] = {}
    for fase in fases:
        validas = [m[fase] for m in mediciones.values() if fase in m and m[fase]["I"] >= UMBRAL_CORRIENTE_A]
        if not validas:
            resultado[fase] = {"n": 0, "veredicto": "SIN_DATOS"}
            continue
        p_media = sum(v["P"] for v in validas) / len(validas)
        frac_neg = sum(1 for v in validas if v["P"] < 0) / len(validas)
        angulo: float | None = None
        if all(not math.isnan(v["Q"]) for v in validas):
            suma_q = sum(v["Q"] for v in validas)
            suma_p = sum(v["P"] for v in validas)
            angulo = math.degrees(math.atan2(suma_q, suma_p))
        if frac_neg > UMBRAL_FRACCION_P_NEGATIVA:
            veredicto = "P_NEGATIVA: posible TI invertido o polaridad cruzada"
        else:
            veredicto = "P_POSITIVA: sin inversión aparente"
        resultado[fase] = {
            "n": len(validas),
            "p_media_w": round(p_media, 1),
            "fraccion_p_negativa": round(frac_neg, 3),
            "angulo_v_i_deg": None if angulo is None else round(angulo, 1),
            "veredicto": veredicto,
        }
    return resultado


def registros_para_ranking(mediciones: dict[str, dict[str, Medicion]], fases: list[str]) -> list[dict] | None:
    """Convierte el CSV al formato de `rankear_candidatos` (p_r, q_r, s_r, fp_r...). None si falta Q."""
    registros: list[dict] = []
    for m in mediciones.values():
        if not all(f in m and not math.isnan(m[f]["Q"]) for f in fases):
            continue
        reg: dict[str, float] = {}
        for f in fases:
            v, i, p, q = m[f]["V"], m[f]["I"], m[f]["P"], m[f]["Q"]
            s = v * i
            key = f.lower()
            reg[f"p_{key}"] = p
            reg[f"q_{key}"] = q
            reg[f"s_{key}"] = s
            reg[f"fp_{key}"] = (abs(p) / s) if s > 0 else 0.0
        registros.append(reg)
    return registros or None


def diagnosticar(ruta: Path, fases: list[str]) -> dict:
    mediciones = leer_mediciones(ruta)
    resultado = {
        "instantes": len(mediciones),
        "por_fase": estadisticas_por_fase(mediciones, fases),
        "candidatos": [],
    }
    registros = registros_para_ranking(mediciones, fases)
    if registros is not None and len(fases) >= 2:
        candidatos = DiagnosticoTIService.rankear_candidatos(registros, tuple(fases))
        resultado["candidatos"] = [
            {"orden": "-".join(c.asociacion_tension_corriente), "invertido": c.polaridad_ti, "score": round(c.score, 4)}
            for c in candidatos[:3]
        ]
    return resultado


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Análisis por fase de un CSV de mediciones (solo lectura).")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--fases", default="R,S,T", help="Fases con TI, por ejemplo R,S")
    args = parser.parse_args(argumentos)
    fases = [f.strip().upper() for f in args.fases.split(",") if f.strip()]
    resultado = diagnosticar(args.csv, fases)
    print(f"Instantes analizados: {resultado['instantes']}")
    for fase, datos in resultado["por_fase"].items():
        print(f"Fase {fase}: {datos}")
    if resultado["candidatos"]:
        print("Ranking existente (orden x polaridad global):")
        for c in resultado["candidatos"]:
            print(f"  {c}")
        if len({c["score"] for c in resultado["candidatos"]}) == 1:
            print("  Empate: el ranking no discrimina con estos datos. Usar el veredicto por fase.")
    else:
        print("Sin ranking: el CSV no trae Q en todas las fases (el ranking necesita Q para la coherencia).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

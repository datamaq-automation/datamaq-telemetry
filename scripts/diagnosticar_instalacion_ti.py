#!/usr/bin/env python3
"""Script de diagnóstico metrológico y auditoría de cableado de TIs (Transformadores de Corriente).

Permite diagnosticar anomalías críticas de instalación en campo:
- TIs conectados a la misma fase física (duplicación / cascada de TIs).
- TIs invertidos en polaridad (sentido K->L o bornes S1-S2).
- Cruce de TIs entre fases (CT mismatch con tensión de otra fase).
- Fases en vacío o desbalances severos.

Uso:
  # Modo Simulación / Comprobación rápida:
  venv/bin/python scripts/diagnosticar_instalacion_ti.py --simular --ir 286.6 --is 286.5 --fpr 0.02 --fps 0.85 --fases R,S

  # Modo Conectado a Base de Datos (Inspección de últimas lecturas):
  venv/bin/python scripts/diagnosticar_instalacion_ti.py --mac D48C49F035A8 --muestras 5
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase  # noqa: E402
from src.domain.telemetria.services import AnalizadorCalidadEnergiaService  # noqa: E402
from src.domain.telemetria.value_objects import (  # noqa: E402
    Corriente,
    FactorPotencia,
    PotenciaActiva,
    PotenciaReactiva,
    Tension,
)


@dataclass
class ResultadoDiagnostico:
    estado_general: str  # OK, ADVERTENCIA, CRITICO
    hallazgos: list[str]
    recomendaciones: list[str]


def calcular_angulo_fp(fp: float | None) -> float:
    """Calcula el ángulo de desfasaje phi en grados a partir del FP."""
    if fp is None:
        return 0.0
    val = max(-1.0, min(1.0, fp))
    return math.degrees(math.acos(val))


def diagnosticar_lectura(
    lectura: LecturaInstantanea,
    fases_con_ti: list[str],
    tipo_instalacion: str = "CONSUMO",
) -> ResultadoDiagnostico:
    """Ejecuta el diagnóstico metrológico completo sobre una lectura instantánea."""
    hallazgos: list[str] = []
    recomendaciones: list[str] = []
    es_critico = False
    es_advertencia = False

    # 1. Evaluar TIs en misma fase (Duplicación)
    alertas_misma_fase = AnalizadorCalidadEnergiaService.evaluar_alerta_tis_en_misma_fase(
        dispositivo_id=lectura.dispositivo_id or "diagnostico",
        lectura=lectura,
        tipo_instalacion=tipo_instalacion,
        fases_con_ti=fases_con_ti,
    )
    for a in alertas_misma_fase:
        es_critico = True
        hallazgos.append(f"[CRÍTICO] TIs en la misma fase: {a.mensaje}")
        recomendaciones.append(
            f"Fase {a.fase}: Verificar el cableado en tablero. Uno de los dos TIs está abrazando "
            f"el conductor de la otra fase o conectado en cascada al mismo secundario. "
            f"Reubicar el sensor toroidal en su fase correspondiente."
        )

    # 2. Evaluar TIs invertidos
    alertas_ti_inv = AnalizadorCalidadEnergiaService.evaluar_alerta_ti_invertido(
        dispositivo_id=lectura.dispositivo_id or "diagnostico",
        lectura=lectura,
        tipo_instalacion=tipo_instalacion,
        fases_con_ti=fases_con_ti,
    )
    for a in alertas_ti_inv:
        es_advertencia = True
        hallazgos.append(f"[ADVERTENCIA] TI Invertido: {a.mensaje}")
        recomendaciones.append(
            f"Fase {a.fase}: Invertir la polaridad de los bornes secundarios (S1/S2) "
            f"o rotar 180° la flecha de flujo de corriente (K->L) en el toroide."
        )

    # 3. Evaluar Cruce de TIs
    alertas_cruce = AnalizadorCalidadEnergiaService.evaluar_alerta_cruce_ti(
        dispositivo_id=lectura.dispositivo_id or "diagnostico",
        lectura=lectura,
        tipo_instalacion=tipo_instalacion,
        fases_con_ti=fases_con_ti,
    )
    for a in alertas_cruce:
        # Solo reportar si no fue ya diagnosticado como TIs en misma fase
        if not any(a.fase in amf.fase for amf in alertas_misma_fase):
            es_advertencia = True
            hallazgos.append(f"[ADVERTENCIA] Cruce de TI: {a.mensaje}")
            recomendaciones.append(
                f"Fase {a.fase}: Verificar coincidencia entre la bornera de tensión (V) "
                f"y la entrada de corriente (I) del medidor."
            )

    # 4. Evaluar Sobrecompensación reactiva
    alerta_sobrecomp = AnalizadorCalidadEnergiaService.evaluar_alerta_sobrecompensacion_reactiva(
        dispositivo_id=lectura.dispositivo_id or "diagnostico",
        lectura=lectura,
    )
    if alerta_sobrecomp:
        if alertas_misma_fase:
            hallazgos.append(
                f"[INFO] Reactiva Capacitiva ({alerta_sobrecomp.valor_medido:.1f} VAr): "
                f"Inducida ficticiamente por el desfasaje angular de los TIs en la misma fase."
            )
        else:
            es_advertencia = True
            hallazgos.append(f"[ADVERTENCIA] Sobrecompensación reactiva: {alerta_sobrecomp.mensaje}")
            recomendaciones.append("Verificar banco de capacitores: posible exceso de inyección reactiva en vacío.")

    if not hallazgos:
        estado = "OK"
        hallazgos.append("Parámetros fasoriales dentro de los rangos normales de operación.")
        recomendaciones.append("Instalación y conexionado validados correctamente.")
    elif es_critico:
        estado = "CRITICO"
    elif es_advertencia:
        estado = "ADVERTENCIA"
    else:
        estado = "INFO"

    return ResultadoDiagnostico(estado_general=estado, hallazgos=hallazgos, recomendaciones=recomendaciones)


def imprimir_informe_fasorial(
    lectura: LecturaInstantanea,
    fases_con_ti: list[str],
    resultado: ResultadoDiagnostico,
) -> None:
    """Imprime el informe de diagnóstico en consola."""
    print("=" * 80)
    print(" DATAMAQ TELEMETRY — AUDITORÍA Y DIAGNÓSTICO METROLÓGICO DE TIs")
    print("=" * 80)

    fases_dict = {
        "R": lectura.fase_r,
        "S": lectura.fase_s,
        "T": lectura.fase_t,
    }

    print("\n--- ESTADO METROLÓGICO POR CANAL ---")
    print(
        f"{'Fase':<6} | {'V (V)':<8} | {'I (A)':<8} | {'P (kW)':<10} | {'Q (kVAr)':<10} | {'FP':<6} | {'phi (°)':<8} | {'TI Habilitado'}"
    )
    print("-" * 80)

    for f_nom in ("R", "S", "T"):
        med = fases_dict[f_nom]
        v_val = med.tension.voltios if med.tension else 0.0
        i_val = med.corriente.amperios if med.corriente else 0.0
        p_val = (med.potencia_activa.vatios / 1000.0) if med.potencia_activa else 0.0
        q_val = (med.potencia_reactiva.var / 1000.0) if med.potencia_reactiva else 0.0
        fp_val = med.factor_potencia.valor if med.factor_potencia else 0.0
        phi_deg = calcular_angulo_fp(fp_val)
        ti_hab = "SÍ" if f_nom in fases_con_ti else "NO (En vacío / Sin TI)"

        print(
            f"{f_nom:<6} | {v_val:<8.1f} | {i_val:<8.1f} | {p_val:<10.2f} | {q_val:<10.2f} | {fp_val:<6.2f} | {phi_deg:<8.1f} | {ti_hab}"
        )

    print("-" * 80)
    p_tot = (lectura.potencia_activa_total.vatios / 1000.0) if lectura.potencia_activa_total else 0.0
    q_tot = (lectura.potencia_reactiva_total.var / 1000.0) if lectura.potencia_reactiva_total else 0.0
    fp_tot = lectura.factor_potencia_total.valor if lectura.factor_potencia_total else 0.0
    print(f"TOTAL: P={p_tot:.2f} kW | Q={q_tot:.2f} kVAr | FP={fp_tot:.2f}")

    print("\n--- RESULTADO DEL DIAGNÓSTICO ---")
    color_map = {
        "OK": "\033[92m[OK]\033[0m",
        "ADVERTENCIA": "\033[93m[ADVERTENCIA]\033[0m",
        "CRITICO": "\033[91m[CRÍTICO]\033[0m",
        "INFO": "\033[94m[INFO]\033[0m",
    }
    tag = color_map.get(resultado.estado_general, f"[{resultado.estado_general}]")
    print(f"Estado General: {tag} {resultado.estado_general}")

    print("\nHallazgos:")
    for h in resultado.hallazgos:
        print(f"  * {h}")

    print("\nAcciones Recomendadas:")
    for r in resultado.recomendaciones:
        print(f"  -> {r}")
    print("=" * 80)


def simular_diagnostico(args: argparse.Namespace) -> int:
    """Ejecuta simulación con valores pasados por CLI."""
    fases_con_ti = [f.strip().upper() for f in args.fases.split(",")]

    p_r = args.pr if args.pr is not None else (args.vr * args.ir * args.fpr)
    q_r = args.qr if args.qr is not None else (args.vr * args.ir * math.sin(math.acos(max(-1.0, min(1.0, args.fpr)))))
    p_s = args.ps if args.ps is not None else (args.vs * args.is_ * args.fps)
    q_s = args.qs if args.qs is not None else (args.vs * args.is_ * math.sin(math.acos(max(-1.0, min(1.0, args.fps)))))
    p_t = args.pt if args.pt is not None else (args.vt * args.it * args.fpt)
    q_t = args.qt if args.qt is not None else (args.vt * args.it * math.sin(math.acos(max(-1.0, min(1.0, args.fpt)))))

    lectura = LecturaInstantanea(
        id=None,
        dispositivo_id="simulacion",
        registrado_en=None,
        fase_r=MedicionFase(
            tension=Tension(args.vr),
            corriente=Corriente(args.ir),
            potencia_activa=PotenciaActiva(p_r),
            potencia_reactiva=PotenciaReactiva(q_r),
            factor_potencia=FactorPotencia(args.fpr),
        ),
        fase_s=MedicionFase(
            tension=Tension(args.vs),
            corriente=Corriente(args.is_),
            potencia_activa=PotenciaActiva(p_s),
            potencia_reactiva=PotenciaReactiva(q_s),
            factor_potencia=FactorPotencia(args.fps),
        ),
        fase_t=MedicionFase(
            tension=Tension(args.vt),
            corriente=Corriente(args.it),
            potencia_activa=PotenciaActiva(p_t),
            potencia_reactiva=PotenciaReactiva(q_t),
            factor_potencia=FactorPotencia(args.fpt),
        ),
        potencia_activa_total=PotenciaActiva(p_r + p_s + p_t),
        potencia_reactiva_total=PotenciaReactiva(q_r + q_s + q_t),
        factor_potencia_total=FactorPotencia(args.fps),
    )

    res = diagnosticar_lectura(lectura, fases_con_ti, tipo_instalacion=args.tipo_instalacion)
    imprimir_informe_fasorial(lectura, fases_con_ti, res)
    return 1 if res.estado_general == "CRITICO" else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auditoría metrológica y diagnóstico de instalación de Transformadores de Corriente (TIs)"
    )
    parser.add_argument("--simular", action="store_true", help="Ejecutar en modo simulación con parámetros de terminal")
    parser.add_argument("--mac", type=str, help="Dirección MAC del medidor (ej. D48C49F035A8)")
    parser.add_argument("--dispositivo-id", type=str, help="UUID del dispositivo")
    parser.add_argument("--fases", type=str, default="R,S,T", help="Fases equipadas con TI (ej. R,S o R,S,T)")
    parser.add_argument("--tipo-instalacion", type=str, default="CONSUMO", choices=["CONSUMO", "GENERACION_FV"])

    # Parámetros de simulación
    parser.add_argument("--vr", type=float, default=220.0, help="Tensión R (V)")
    parser.add_argument("--vs", type=float, default=220.0, help="Tensión S (V)")
    parser.add_argument("--vt", type=float, default=220.0, help="Tensión T (V)")
    parser.add_argument("--ir", type=float, default=0.0, help="Corriente R (A)")
    parser.add_argument("--is", dest="is_", type=float, default=0.0, help="Corriente S (A)")
    parser.add_argument("--it", type=float, default=0.0, help="Corriente T (A)")
    parser.add_argument("--fpr", type=float, default=1.0, help="Factor de Potencia R")
    parser.add_argument("--fps", type=float, default=1.0, help="Factor de Potencia S")
    parser.add_argument("--fpt", type=float, default=1.0, help="Factor de Potencia T")
    parser.add_argument("--pr", type=float, default=None, help="Potencia Activa R (W) opcional")
    parser.add_argument("--ps", type=float, default=None, help="Potencia Activa S (W) opcional")
    parser.add_argument("--pt", type=float, default=None, help="Potencia Activa T (W) opcional")
    parser.add_argument("--qr", type=float, default=None, help="Potencia Reactiva R (VAr) opcional")
    parser.add_argument("--qs", type=float, default=None, help="Potencia Reactiva S (VAr) opcional")
    parser.add_argument("--qt", type=float, default=None, help="Potencia Reactiva T (VAr) opcional")

    args = parser.parse_args()

    if args.simular or (args.ir > 0 or args.is_ > 0 or args.it > 0):
        return simular_diagnostico(args)

    if not args.mac and not args.dispositivo_id:
        print("Debe especificar --simular (con corrientes) o un identificador (--mac o --dispositivo-id).")
        parser.print_help()
        return 2

    # Modo Conectado a BD
    try:
        from src.infrastructure.sqlalchemy.database import get_session_factory
        from src.infrastructure.sqlalchemy.repositories.dispositivos_repository import MySQLDispositivosRepository
        from src.infrastructure.sqlalchemy.repositories.telemetria_repository import MySQLTelemetriaRepository

        session_factory = get_session_factory()
        with session_factory() as session:
            repo_disp = MySQLDispositivosRepository(session)
            repo_telem = MySQLTelemetriaRepository(session)

            dispositivo = None
            if args.mac:
                from src.domain.telemetria.value_objects import MacAddress

                dispositivo = repo_disp.obtener_por_mac(MacAddress(args.mac))
            elif args.dispositivo_id:
                dispositivo = repo_disp.obtener_por_id(args.dispositivo_id)

            if not dispositivo:
                print(f"Error: Dispositivo no encontrado ({args.mac or args.dispositivo_id}).")
                return 1

            lectura = repo_telem.obtener_ultima_lectura(dispositivo.id)
            if not lectura:
                print(f"No se encontraron lecturas de telemetría para el dispositivo {dispositivo.id}.")
                return 1

            fases_ti = [f.strip().upper() for f in getattr(dispositivo, "fases_con_ti", "R,S,T").split(",")]
            tipo_inst = getattr(dispositivo, "tipo_instalacion", "CONSUMO")

            res = diagnosticar_lectura(lectura, fases_ti, tipo_instalacion=tipo_inst)
            imprimir_informe_fasorial(lectura, fases_ti, res)
            return 1 if res.estado_general == "CRITICO" else 0
    except Exception as e:
        print(f"Error al conectar con la base de datos: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
